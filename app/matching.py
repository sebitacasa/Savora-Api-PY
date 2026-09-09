"""
Lógica de matching ingredientes → recetas. Pura (sin DB, sin FastAPI)
para poder testearla unitariamente.

Reglas de negocio:
 - Normalización: minúsculas, sin espacios al borde, espacios internos colapsados.
 - Resolución de ingredientes: nombre canónico o cualquier sinónimo; si no
   matchea y termina en "s"/"es", se reintenta en singular naive.
 - Solo se sugieren recetas con al menos 1 ingrediente matcheado.
 - Ranking: mayor score primero (matcheados / total de la receta); a igual
   score, menos faltantes primero; a igual todo, orden alfabético.
 - Filtro de dieta jerárquico: "vegan" ⊂ "vegetarian". Filtrar por
   vegetarian incluye recetas veganas; filtrar por vegan solo veganas;
   "mit_meat" solo platos con carne. Sin filtro, se sugiere todo.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal, Optional

Diet = Literal["vegan", "vegetarian", "mit_meat"]
DIETS: tuple[Diet, ...] = ("vegan", "vegetarian", "mit_meat")


@dataclass
class RecipeRecord:
    id: int
    title: str
    diet: Diet
    ingredients: list[str]  # nombres canónicos


@dataclass
class Suggestion:
    id: int
    title: str
    diet: Diet
    matched: list[str]
    missing: list[str]
    score: float  # 0..1, redondeado a 2 decimales


@dataclass
class SuggestResult:
    suggestions: list[Suggestion]
    unknown_ingredients: list[str]  # inputs que no resolvimos a ningún ingrediente conocido
    resolved_ingredients: list[str] = field(default_factory=list)  # canónicos resueltos


def normalize(input_: str) -> str:
    return re.sub(r"\s+", " ", input_.strip().lower())


def resolve_ingredient(input_: str, synonym_map: dict[str, str]) -> Optional[str]:
    """synonym_map: alias normalizado -> nombre canónico (incluye el canónico
    como alias de sí mismo)."""
    normalized = normalize(input_)
    if len(normalized) == 0:
        return None

    direct = synonym_map.get(normalized)
    if direct:
        return direct

    # Singular naive: "potatoes" -> "potato", "eggs" -> "egg"
    for suffix in ("es", "s"):
        if normalized.endswith(suffix):
            singular = synonym_map.get(normalized[: -len(suffix)])
            if singular:
                return singular
    return None


def diet_matches(recipe_diet: Diet, filter_: Optional[Diet] = None) -> bool:
    if filter_ is None:
        return True
    if filter_ == "vegetarian":
        return recipe_diet in ("vegetarian", "vegan")
    return recipe_diet == filter_


def suggest(
    inputs: list[str],
    recipes: list[RecipeRecord],
    synonym_map: dict[str, str],
    diet: Optional[Diet] = None,
) -> SuggestResult:
    resolved: set[str] = set()
    unknown_ingredients: list[str] = []

    for input_ in inputs:
        canonical = resolve_ingredient(input_, synonym_map)
        if canonical:
            resolved.add(canonical)
        elif len(normalize(input_)) > 0:
            unknown_ingredients.append(input_.strip())

    suggestions: list[Suggestion] = []
    for recipe in recipes:
        if not diet_matches(recipe.diet, diet):
            continue

        matched = [i for i in recipe.ingredients if i in resolved]
        if len(matched) == 0:
            continue

        missing = [i for i in recipe.ingredients if i not in resolved]
        suggestions.append(
            Suggestion(
                id=recipe.id,
                title=recipe.title,
                diet=recipe.diet,
                matched=matched,
                missing=missing,
                score=round((len(matched) / len(recipe.ingredients)) * 100) / 100,
            )
        )

    suggestions.sort(key=lambda s: (-s.score, len(s.missing), s.title))

    return SuggestResult(
        suggestions=suggestions,
        unknown_ingredients=unknown_ingredients,
        resolved_ingredients=list(resolved),
    )
