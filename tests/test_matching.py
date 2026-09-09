import pytest

from app.matching import RecipeRecord, diet_matches, normalize, resolve_ingredient, suggest

SYNONYMS = {
    "potato": "potato",
    "kartoffel": "potato",
    "kartoffeln": "potato",
    "egg": "egg",
    "ei": "egg",
    "eier": "egg",
    "onion": "onion",
    "zwiebel": "onion",
    "zwiebeln": "onion",
    "salt": "salt",
    "salz": "salt",
    "ground beef": "ground beef",
    "hackfleisch": "ground beef",
}

RECIPES = [
    RecipeRecord(1, "Kartoffel-Tortilla", "vegetarian", ["potato", "egg", "onion", "salt"]),
    RecipeRecord(2, "Schnitzel", "mit_meat", ["ground beef", "egg", "salt"]),
    RecipeRecord(3, "Mashed Potatoes", "vegan", ["potato", "salt"]),
]


# TC-API-01
def test_normalize_baja_minusculas_recorta_y_colapsa_espacios():
    assert normalize("  Ground   Beef  ") == "ground beef"


# TC-API-02: sinónimos alemanes resuelven al canónico inglés
@pytest.mark.parametrize("input_", ["potato", "Kartoffel", "KARTOFFELN", "kartoffel"])
def test_resolve_ingredient_sinonimos_alemanes(input_):
    assert resolve_ingredient(input_, SYNONYMS) == "potato"


# TC-API-03: plural inglés naive
def test_resolve_ingredient_plurales_ingleses():
    assert resolve_ingredient("potatoes", SYNONYMS) == "potato"
    assert resolve_ingredient("onions", SYNONYMS) == "onion"
    assert resolve_ingredient("eggs", SYNONYMS) == "egg"


# TC-API-04
def test_resolve_ingredient_desconocidos_o_vacios():
    assert resolve_ingredient("unicorn", SYNONYMS) is None
    assert resolve_ingredient("   ", SYNONYMS) is None


# TC-API-05: la regla de negocio clave
def test_diet_matches_vegetarian_incluye_veganas():
    assert diet_matches("vegan", "vegetarian") is True
    assert diet_matches("vegetarian", "vegetarian") is True
    assert diet_matches("mit_meat", "vegetarian") is False


# TC-API-06: vegan es estricto
def test_diet_matches_vegan_excluye_vegetariano_no_vegano():
    assert diet_matches("vegan", "vegan") is True
    assert diet_matches("vegetarian", "vegan") is False


def test_diet_matches_sin_filtro_pasa_todo():
    assert diet_matches("mit_meat") is True


# TC-API-07: score y orden
def test_suggest_ordena_por_proporcion_matcheada():
    result = suggest(["potato", "salt"], RECIPES, SYNONYMS)
    titles = [s.title for s in result.suggestions]
    assert titles == ["Mashed Potatoes", "Kartoffel-Tortilla", "Schnitzel"]
    assert result.suggestions[0].score == 1
    assert result.suggestions[1].missing == ["egg", "onion"]


# TC-API-08: recetas sin ningún match no aparecen
def test_suggest_excluye_recetas_sin_match():
    result = suggest(["hackfleisch"], RECIPES, SYNONYMS)
    assert [s.title for s in result.suggestions] == ["Schnitzel"]


# TC-API-09: combinación matching + dieta
def test_suggest_aplica_filtro_de_dieta():
    result = suggest(["potato", "egg", "salt"], RECIPES, SYNONYMS, "vegetarian")
    assert [s.title for s in result.suggestions] == ["Mashed Potatoes", "Kartoffel-Tortilla"]


# TC-API-10: reporta lo que no entendió
def test_suggest_devuelve_ingredientes_no_reconocidos():
    result = suggest(["potato", "unicorn", "dragon"], RECIPES, SYNONYMS)
    assert result.unknown_ingredients == ["unicorn", "dragon"]


# TC-API-11: duplicados en el input no inflan el score
def test_suggest_duplicados_cuentan_una_sola_vez():
    result = suggest(["potato", "potatoes", "Kartoffel"], RECIPES, SYNONYMS)
    mashed = next(s for s in result.suggestions if s.title == "Mashed Potatoes")
    assert mashed.matched == ["potato"]
    assert mashed.score == 0.5
