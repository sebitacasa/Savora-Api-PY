"""
Cliente de Spoonacular (https://spoonacular.com/food-api), usado como
catálogo externo de recetas. La app nunca llama a Spoonacular directo:
este backend hace de proxy, así la API key no viaja al cliente y podemos
cachear para no quemar el cupo del tier gratuito.

Decisiones:
 - Usamos /recipes/complexSearch (y no findByIngredients) porque soporta
   el filtro de dieta además de includeIngredients.
 - Los canónicos de nuestra base ya están en inglés (lo que Spoonacular
   entiende), así que se mandan directo, sin traducción.
 - Dieta: vegan y vegetarian se pasan directo. "mit_meat" no existe en
   Spoonacular, así que en ese caso no se filtra (limitación documentada).
 - Caché en memoria con TTL de 1 h por combinación ingredientes+dieta.
 - Timeout de 5 s: si el servicio externo está lento, no colgamos nuestra
   respuesta.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Optional

import httpx

from .matching import Diet


@dataclass
class ExternalSuggestion:
    id: int
    title: str
    image: Optional[str]
    matched_count: int
    missing_count: int
    source: str = "spoonacular"


@dataclass
class ExternalRecipeDetail:
    id: int
    title: str
    image: Optional[str]
    servings: Optional[int]
    ready_in_minutes: Optional[int]
    source_url: Optional[str]
    ingredients: list[dict]  # [{ "name": str, "original": str }]
    instructions: list[str]


def _strip_html(html: Optional[str]) -> list[str]:
    if not html:
        return []
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", html)).strip()
    return [text] if text else []


def map_diet(diet: Optional[Diet]) -> Optional[str]:
    if diet in ("vegan", "vegetarian"):
        return diet
    return None  # mit_meat o sin filtro: Spoonacular no tiene dieta "con carne"


class SpoonacularClient:
    def __init__(
        self,
        api_key: str,
        client: Optional[httpx.AsyncClient] = None,
        ttl_seconds: float = 60 * 60,
        timeout_seconds: float = 5.0,
    ):
        self.api_key = api_key
        self.client = client or httpx.AsyncClient()
        self.ttl_seconds = ttl_seconds
        self.timeout_seconds = timeout_seconds
        self._cache: dict[str, tuple[float, list[ExternalSuggestion]]] = {}
        self._detail_cache: dict[int, tuple[float, ExternalRecipeDetail]] = {}

    async def search(
        self, canonicals: list[str], diet: Optional[Diet] = None
    ) -> list[ExternalSuggestion]:
        if len(canonicals) == 0:
            return []

        key = f"{','.join(sorted(canonicals))}|{map_diet(diet) or ''}"
        cached = self._cache.get(key)
        if cached and time.monotonic() - cached[0] < self.ttl_seconds:
            return cached[1]

        params = {
            "includeIngredients": ",".join(canonicals),
            "fillIngredients": "true",
            "sort": "max-used-ingredients",
            "number": "6",
            "apiKey": self.api_key,
        }
        spoon_diet = map_diet(diet)
        if spoon_diet:
            params["diet"] = spoon_diet

        res = await self.client.get(
            "https://api.spoonacular.com/recipes/complexSearch",
            params=params,
            timeout=self.timeout_seconds,
        )

        if res.status_code in (402, 429):
            raise RuntimeError("Spoonacular daily quota exhausted.")
        if res.status_code >= 400:
            raise RuntimeError(f"Spoonacular responded {res.status_code}.")

        body = res.json()
        data = [
            ExternalSuggestion(
                id=r["id"],
                title=r["title"],
                image=r.get("image"),
                matched_count=r.get("usedIngredientCount", 0),
                missing_count=r.get("missedIngredientCount", 0),
            )
            for r in body.get("results", [])
        ]

        self._cache[key] = (time.monotonic(), data)
        return data

    async def get_recipe_detail(self, id_: int) -> ExternalRecipeDetail:
        """Detalle completo de una receta externa (ingredientes + instrucciones),
        usado por la pantalla de detalle de "Ideas from the internet"."""
        cached = self._detail_cache.get(id_)
        if cached and time.monotonic() - cached[0] < self.ttl_seconds:
            return cached[1]

        res = await self.client.get(
            f"https://api.spoonacular.com/recipes/{id_}/information",
            params={"apiKey": self.api_key},
            timeout=self.timeout_seconds,
        )

        if res.status_code in (402, 429):
            raise RuntimeError("Spoonacular daily quota exhausted.")
        if res.status_code == 404:
            raise RuntimeError("Recipe not found.")
        if res.status_code >= 400:
            raise RuntimeError(f"Spoonacular responded {res.status_code}.")

        body = res.json()
        steps = [
            step["step"]
            for section in body.get("analyzedInstructions", [])
            for step in section.get("steps", [])
            if step.get("step")
        ]

        data = ExternalRecipeDetail(
            id=body["id"],
            title=body["title"],
            image=body.get("image"),
            servings=body.get("servings"),
            ready_in_minutes=body.get("readyInMinutes"),
            source_url=body.get("sourceUrl"),
            ingredients=[
                {"name": i.get("name", ""), "original": i.get("original", i.get("name", ""))}
                for i in body.get("extendedIngredients", [])
            ],
            instructions=steps if steps else _strip_html(body.get("instructions")),
        )

        self._detail_cache[id_] = (time.monotonic(), data)
        return data
