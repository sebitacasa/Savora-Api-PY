import httpx
import pytest
from fastapi.testclient import TestClient

from app.db import create_db
from app.main import create_app
from app.spoonacular import SpoonacularClient


@pytest.fixture()
def db():
    database = create_db(":memory:")
    yield database
    database.close()


@pytest.fixture()
def client(db):
    app = create_app(db)
    return TestClient(app)


def mock_spoonacular(handler, api_key="key") -> SpoonacularClient:
    """handler(request: httpx.Request) -> httpx.Response"""
    transport = httpx.MockTransport(handler)
    async_client = httpx.AsyncClient(transport=transport)
    return SpoonacularClient(api_key, client=async_client)


# TC-API-20
def test_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


# TC-API-21
def test_lista_recetas_del_seed(client):
    res = client.get("/api/recipes")
    assert res.status_code == 200
    recipes = res.json()["recipes"]
    assert len(recipes) >= 10
    assert "title" in recipes[0]
    assert "diet" in recipes[0]
    assert "ingredients" in recipes[0]


# TC-API-22
def test_diet_vegetarian_incluye_vegetarianas_y_veganas(client):
    res = client.get("/api/recipes?diet=vegetarian")
    assert res.status_code == 200
    diets = [r["diet"] for r in res.json()["recipes"]]
    assert len(diets) > 0
    assert "mit_meat" not in diets


def test_diet_vegan_devuelve_solo_veganas(client):
    res = client.get("/api/recipes?diet=vegan")
    diets = [r["diet"] for r in res.json()["recipes"]]
    assert len(diets) > 0
    assert set(diets) == {"vegan"}


# TC-API-23
def test_diet_invalido_responde_400(client):
    res = client.get("/api/recipes?diet=paleo")
    assert res.status_code == 400
    assert "diet must be one of" in res.json()["error"]


def test_detalle_de_receta_completo(client):
    res = client.get("/api/recipes/1")
    assert res.status_code == 200
    recipe = res.json()["recipe"]
    assert "title" in recipe
    assert "instructions" in recipe
    assert len(recipe["instructions"]) > 0
    assert isinstance(recipe["ingredients"], list)
    assert "name" in recipe["ingredients"][0]
    assert "quantity" in recipe["ingredients"][0]


def test_id_inexistente_responde_404(client):
    res = client.get("/api/recipes/99999")
    assert res.status_code == 404
    assert "not found" in res.json()["error"].lower()


def test_id_no_numerico_responde_400(client):
    res = client.get("/api/recipes/abc")
    assert res.status_code == 400


# TC-API-54
def test_external_sin_spoonacular_configurado_503(client):
    res = client.get("/api/external/715415")
    assert res.status_code == 503
    assert "not configured" in res.json()["error"]


def test_external_id_no_numerico_400(client):
    res = client.get("/api/external/abc")
    assert res.status_code == 400


# TC-API-55
def test_external_con_spoonacular_devuelve_detalle(db):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": 715415,
                "title": "Red Lentil Soup",
                "image": "https://img.spoonacular.com/recipes/715415-312x231.jpg",
                "servings": 4,
                "readyInMinutes": 30,
                "sourceUrl": "https://example.com/red-lentil-soup",
                "analyzedInstructions": [{"steps": [{"step": "Simmer everything."}]}],
                "extendedIngredients": [{"name": "lentils", "original": "2 cups red lentils"}],
            },
        )

    app = create_app(db, spoonacular=mock_spoonacular(handler))
    res = TestClient(app).get("/api/external/715415")

    assert res.status_code == 200
    recipe = res.json()["recipe"]
    assert recipe["title"] == "Red Lentil Soup"
    assert recipe["instructions"] == ["Simmer everything."]
    assert recipe["ingredients"] == [{"name": "lentils", "original": "2 cups red lentils"}]


# TC-API-56
def test_external_receta_inexistente_404(db):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={})

    app = create_app(db, spoonacular=mock_spoonacular(handler))
    res = TestClient(app).get("/api/external/999999")
    assert res.status_code == 404


# TC-API-57
def test_external_si_spoonacular_falla_502(db):
    def handler(request: httpx.Request) -> httpx.Response:
        raise RuntimeError("network down")

    app = create_app(db, spoonacular=mock_spoonacular(handler))
    res = TestClient(app).get("/api/external/1")
    assert res.status_code == 502
    assert res.json()["error"] == "network down"


# TC-API-24: caso feliz mezclando inglés y alemán
def test_sugiere_recetas_ingles_y_aleman(client):
    res = client.post(
        "/api/suggestions",
        json={"ingredients": ["salt", "pfeffer", "zwiebel", "potatoes", "eggs"]},
    )
    assert res.status_code == 200
    body = res.json()
    titles = [s["title"] for s in body["suggestions"]]
    assert "Kartoffel-Tortilla" in titles
    assert titles[0] == "Kartoffel-Tortilla"
    assert body["suggestions"][0]["score"] == 0.8
    assert body["suggestions"][0]["missing"] == ["olive oil"]


# TC-API-25: matching + dieta juntos (input 100% alemán)
def test_diet_vegan_no_sugiere_tortilla_pero_si_wok(client):
    res = client.post(
        "/api/suggestions",
        json={"ingredients": ["zwiebel", "karotten", "salz"], "diet": "vegan"},
    )
    assert res.status_code == 200
    titles = [s["title"] for s in res.json()["suggestions"]]
    assert "Gemüse-Wok" in titles
    assert "Kartoffel-Tortilla" not in titles


# TC-API-26: validaciones
def test_sin_body_responde_400(client):
    res = client.post("/api/suggestions", json={})
    assert res.status_code == 400
    assert "ingredients is required" in res.json()["error"]


@pytest.mark.parametrize("ingredients", [[], ["   ", ""]])
def test_array_vacio_o_solo_espacios_400(client, ingredients):
    res = client.post("/api/suggestions", json={"ingredients": ingredients})
    assert res.status_code == 400
    assert "at least one ingredient" in res.json()["error"]


def test_mas_de_30_ingredientes_400(client):
    ingredients = [f"ing{i}" for i in range(31)]
    res = client.post("/api/suggestions", json={"ingredients": ingredients})
    assert res.status_code == 400
    assert "Maximum 30" in res.json()["error"]


def test_ingredientes_no_texto_400(client):
    res = client.post("/api/suggestions", json={"ingredients": ["salt", 42, None]})
    assert res.status_code == 400


def test_diet_invalida_400(client):
    res = client.post("/api/suggestions", json={"ingredients": ["salt"], "diet": "keto"})
    assert res.status_code == 400


# TC-API-27
def test_informa_unknown_ingredients_sin_fallar(client):
    res = client.post(
        "/api/suggestions", json={"ingredients": ["potato", "papa", "kryptonite"]}
    )
    assert res.status_code == 200
    assert res.json()["unknownIngredients"] == ["papa", "kryptonite"]


# TC-API-28
def test_solo_desconocidos_devuelve_sugerencias_vacias(client):
    res = client.post("/api/suggestions", json={"ingredients": ["kryptonite"]})
    assert res.status_code == 200
    body = res.json()
    assert body["suggestions"] == []
    assert body["unknownIngredients"] == ["kryptonite"]
