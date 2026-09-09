"""
Wooly, la ovejita asistente — un chat con personalidad respaldado por la API
de Claude, con function calling sobre el catálogo real de recetas (nunca
inventa recetas que no existen) y, cuando hace falta, sobre Spoonacular.

Patrón: el cliente manda el mensaje nuevo + el historial de la conversación
(solo turnos de texto, sin exponer el detalle de tool use). Acá adentro
armamos el loop de tool calling internamente por request; lo único que vuelve
al cliente es el texto final de Wooly, el historial actualizado (turnos
planos) y las recetas encontradas (locales y/o de Spoonacular), listas para
que la app arme un link directo a cada una.
"""

from __future__ import annotations

from typing import Optional

from anthropic import AsyncAnthropic

from .db import Db, load_recipes, load_synonym_map
from .matching import Diet, suggest
from .spoonacular import SpoonacularClient

MODEL = "claude-sonnet-4-5"
MAX_TOKENS = 500

SYSTEM_PROMPT = """You are Linna, a friendly little black plush sheep who lives inside the \
Savora cooking app and helps people figure out what to cook.

Personality: warm, playful, a bit silly — the occasional "Baa!" is welcome, but don't overdo \
it. Keep replies short (2-4 sentences), like a text message from a friend, not an essay.

You have two tools:
- `search_recipes` searches the app's own recipe catalog (small, curated, instant).
- `search_spoonacular_recipes` searches a much bigger online catalog. It's slower and has a \
limited daily quota, so only use it when `search_recipes` comes back empty or with weak, \
low-score matches, or when the user explicitly asks for more ideas / something from online.

ALWAYS use a tool before recommending a specific recipe — never invent a recipe or ingredient \
list from memory. Prefer `search_recipes` first. If the user mentions ingredients (in English \
or German), search with those. If nothing is found anywhere, say so honestly and suggest they \
try different ingredients — don't make something up to avoid disappointing them.

If the user isn't asking about food at all, gently steer the conversation back to cooking \
in character, without being preachy about it.
"""

SEARCH_RECIPES_TOOL = {
    "name": "search_recipes",
    "description": (
        "Search the Savora app's own recipe catalog for recipes matching the given "
        "ingredients, optionally filtered by diet. Fast, but only ~10 recipes total."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "ingredients": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Ingredient names the user has on hand, in English or German.",
            },
            "diet": {
                "type": "string",
                "enum": ["vegan", "vegetarian", "mit_meat"],
                "description": "Optional diet filter.",
            },
        },
        "required": ["ingredients"],
    },
}

SEARCH_SPOONACULAR_TOOL = {
    "name": "search_spoonacular_recipes",
    "description": (
        "Search Spoonacular's large online recipe database. Slower and quota-limited — only "
        "use this after search_recipes has already come back empty or weak, or if the user "
        "explicitly asks for more/online ideas."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "ingredients": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Ingredient names, in English (Spoonacular is English-only).",
            },
            "diet": {
                "type": "string",
                "enum": ["vegan", "vegetarian"],
                "description": "Optional diet filter (Spoonacular has no 'with meat' filter).",
            },
        },
        "required": ["ingredients"],
    },
}


def _run_search_recipes(db: Db, tool_input: dict) -> dict:
    ingredients = tool_input.get("ingredients", [])
    diet: Optional[Diet] = tool_input.get("diet")
    result = suggest(ingredients, load_recipes(db), load_synonym_map(db), diet)
    top = result.suggestions[:5]
    matches = [
        {
            "id": s.id,
            "title": s.title,
            "diet": s.diet,
            "score": s.score,
            "matched": s.matched,
            "missing": s.missing,
            "source": "local",
        }
        for s in top
    ]
    return matches, {
        "matches": [{k: v for k, v in m.items() if k != "source"} for m in matches],
        "unknown_ingredients": result.unknown_ingredients,
    }


async def _run_search_spoonacular(spoonacular: SpoonacularClient, tool_input: dict) -> tuple:
    ingredients = tool_input.get("ingredients", [])
    diet: Optional[Diet] = tool_input.get("diet")
    try:
        results = await spoonacular.search(ingredients, diet)
    except Exception as e:
        return [], {"error": str(e)}

    matches = [
        {
            "id": r.id,
            "title": r.title,
            "image": r.image,
            "matchedCount": r.matched_count,
            "missingCount": r.missing_count,
            "source": "spoonacular",
        }
        for r in results
    ]
    return matches, {"matches": matches}


async def ask_wooly(
    client: AsyncAnthropic,
    db: Db,
    message: str,
    history: Optional[list[dict]] = None,
    spoonacular: Optional[SpoonacularClient] = None,
) -> dict:
    """Devuelve { reply, history, recipes, externalRecipes }.

    `history` y el `history` de retorno son turnos planos [{role, content}],
    sin bloques de tool use — eso se resuelve todo internamente en este
    request."""

    working_messages: list[dict] = [*(history or []), {"role": "user", "content": message}]
    found_local: list[dict] = []
    found_external: list[dict] = []

    tools = [SEARCH_RECIPES_TOOL]
    if spoonacular is not None:
        tools.append(SEARCH_SPOONACULAR_TOOL)

    while True:
        response = await client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            tools=tools,
            messages=working_messages,
        )

        if response.stop_reason != "tool_use":
            reply_text = "".join(
                block.text for block in response.content if block.type == "text"
            ).strip()
            updated_history = [
                *(history or []),
                {"role": "user", "content": message},
                {"role": "assistant", "content": reply_text},
            ]
            return {
                "reply": reply_text,
                "history": updated_history,
                "recipes": found_local,
                "externalRecipes": found_external,
            }

        # stop_reason == "tool_use": ejecutamos cada tool_use del turno y
        # seguimos el loop con los resultados agregados a la conversación.
        working_messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue

            if block.name == "search_recipes":
                matches, tool_output = _run_search_recipes(db, block.input)
                found_local = matches
            elif block.name == "search_spoonacular_recipes" and spoonacular is not None:
                matches, tool_output = await _run_search_spoonacular(spoonacular, block.input)
                found_external = matches
            else:
                tool_output = {"error": f"Unknown tool: {block.name}"}

            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": str(tool_output),
                }
            )

        working_messages.append({"role": "user", "content": tool_results})
