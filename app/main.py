"""
API HTTP de Nicy Kitchen.

POST /api/suggestions  { ingredients: string[], diet?: Diet }
  -> { suggestions, unknown_ingredients, resolved_ingredients }
GET  /api/recipes      ?diet=vegan|vegetarian|mit_meat (jerárquico)
GET  /api/recipes/:id  -> detalle completo (ingredientes + cantidades + instrucciones)
GET  /api/external/:id -> detalle de una receta de Spoonacular (requiere spoonacular configurado)
GET  /api/news         ?topic=food|health (default food; requiere news configurado)
GET  /health

Validaciones de /api/suggestions:
 - ingredients: requerido, array de strings, entre 1 y 30 items no vacíos
 - diet: opcional, uno de DIETS
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Optional

from anthropic import AsyncAnthropic
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .assistant import ask_wooly
from .db import Db, load_recipe, load_recipes, load_synonym_map
from .matching import DIETS, Diet, suggest
from .news import NEWS_TOPICS, NewsDataClient
from .spoonacular import SpoonacularClient

MAX_INGREDIENTS = 30


class SuggestionsBody(BaseModel):
    ingredients: Optional[list] = None
    diet: Optional[str] = None


def _parse_diet(value: Optional[str]) -> tuple[Optional[Diet], Optional[str]]:
    if value is None or value == "":
        return None, None
    if value in DIETS:
        return value, None  # type: ignore[return-value]
    return None, f"diet must be one of: {', '.join(DIETS)}."


def create_app(
    db: Db,
    spoonacular: Optional[SpoonacularClient] = None,
    news: Optional[NewsDataClient] = None,
    assistant: Optional[AsyncAnthropic] = None,
) -> FastAPI:
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.db = db
    app.state.spoonacular = spoonacular
    app.state.news = news
    app.state.assistant = assistant

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/recipes")
    def get_recipes(diet: Optional[str] = None):
        parsed_diet, error = _parse_diet(diet)
        if error:
            return JSONResponse(status_code=400, content={"error": error})

        recipes = load_recipes(db)
        if parsed_diet:
            recipes = [
                r
                for r in recipes
                if (r.diet in ("vegetarian", "vegan") if parsed_diet == "vegetarian" else r.diet == parsed_diet)
            ]
        return {"recipes": [asdict(r) for r in recipes]}

    @app.get("/api/recipes/{recipe_id}")
    def get_recipe(recipe_id: str):
        if not recipe_id.lstrip("-").isdigit():
            return JSONResponse(status_code=400, content={"error": "id must be a whole number."})

        recipe = load_recipe(db, int(recipe_id))
        if recipe is None:
            return JSONResponse(status_code=404, content={"error": "Recipe not found."})
        return {"recipe": asdict(recipe)}

    @app.get("/api/external/{recipe_id}")
    async def get_external_recipe(recipe_id: str):
        if not recipe_id.lstrip("-").isdigit():
            return JSONResponse(status_code=400, content={"error": "id must be a whole number."})
        if app.state.spoonacular is None:
            return JSONResponse(
                status_code=503, content={"error": "External catalog is not configured."}
            )

        try:
            recipe = await app.state.spoonacular.get_recipe_detail(int(recipe_id))
            return {"recipe": asdict(recipe)}
        except RuntimeError as e:
            if str(e) == "Recipe not found.":
                return JSONResponse(status_code=404, content={"error": str(e)})
            return JSONResponse(status_code=502, content={"error": str(e)})

    @app.get("/api/news")
    async def get_news(topic: str = "food"):
        if topic not in NEWS_TOPICS:
            return JSONResponse(
                status_code=400,
                content={"error": f"topic must be one of: {', '.join(NEWS_TOPICS)}."},
            )
        if app.state.news is None:
            return JSONResponse(
                status_code=503,
                content={"error": "News source is not configured. Set NEWSDATA_API_KEY."},
            )

        try:
            articles = await app.state.news.get_news(topic)  # type: ignore[arg-type]
            return {"articles": [asdict(a) for a in articles]}
        except Exception as e:
            return JSONResponse(status_code=502, content={"error": str(e)})

    @app.post("/api/suggestions")
    async def post_suggestions(request: Request):
        try:
            body = await request.json()
        except Exception:
            body = {}
        body = body or {}

        ingredients = body.get("ingredients")
        if not isinstance(ingredients, list):
            return JSONResponse(
                status_code=400,
                content={"error": "ingredients is required and must be an array."},
            )
        if not all(isinstance(i, str) for i in ingredients):
            return JSONResponse(status_code=400, content={"error": "All ingredients must be text."})

        non_empty = [i for i in ingredients if i.strip()]
        if len(non_empty) == 0:
            return JSONResponse(status_code=400, content={"error": "Send at least one ingredient."})
        if len(non_empty) > MAX_INGREDIENTS:
            return JSONResponse(
                status_code=400,
                content={"error": f"Maximum {MAX_INGREDIENTS} ingredients per request."},
            )

        parsed_diet, error = _parse_diet(body.get("diet"))
        if error:
            return JSONResponse(status_code=400, content={"error": error})

        result = suggest(non_empty, load_recipes(db), load_synonym_map(db), parsed_diet)

        # Catálogo externo (Spoonacular) detrás de nuestro proxy: si falla o no
        # hay API key, las sugerencias locales se devuelven igual.
        external = None
        external_error = None
        if app.state.spoonacular is not None and len(result.resolved_ingredients) > 0:
            try:
                external = await app.state.spoonacular.search(
                    result.resolved_ingredients, parsed_diet
                )
            except Exception as e:
                external_error = str(e)

        response = {
            "suggestions": [asdict(s) for s in result.suggestions],
            "unknownIngredients": result.unknown_ingredients,
            "resolvedIngredients": result.resolved_ingredients,
        }
        if external is not None:
            response["external"] = [asdict(e) for e in external]
        if external_error:
            response["externalError"] = external_error

        return response

    @app.post("/api/assistant")
    async def post_assistant(request: Request):
        if app.state.assistant is None:
            return JSONResponse(
                status_code=503,
                content={"error": "Wooly's brain is not configured. Set ANTHROPIC_API_KEY."},
            )

        try:
            body = await request.json()
        except Exception:
            body = {}
        body = body or {}

        message = body.get("message")
        if not isinstance(message, str) or not message.strip():
            return JSONResponse(
                status_code=400, content={"error": "message is required and must be text."}
            )

        history = body.get("history")
        if history is not None and not isinstance(history, list):
            return JSONResponse(status_code=400, content={"error": "history must be an array."})

        try:
            result = await ask_wooly(
                app.state.assistant, db, message, history, spoonacular=app.state.spoonacular
            )
        except Exception as e:
            return JSONResponse(
                status_code=502, content={"error": str(e) or "Wooly got distracted by a leaf."}
            )

        return result

    return app
