import httpx
import pytest
from fastapi.testclient import TestClient

from app.db import create_db
from app.main import create_app
from app.spoonacular import SpoonacularClient, map_diet

SAMPLE_RESULT = {
    "id": 715415,
    "title": "Red Lentil Soup",
    "image": "https://img.spoonacular.com/recipes/715415-312x231.jpg",
    "usedIngredientCount": 3,
    "missedIngredientCount": 2,
}


def client_with_handler(handler, api_key="key", ttl_seconds=60 * 60) -> SpoonacularClient:
    transport = httpx.MockTransport(handler)
    return SpoonacularClient(
        api_key, client=httpx.AsyncClient(transport=transport), ttl_seconds=ttl_seconds
    )


def ok_response(results: list) -> httpx.Response:
    return httpx.Response(200, json={"results": results})


# TC-API-41
def test_map_diet():
    assert map_diet("vegan") == "vegan"
    assert map_diet("vegetarian") == "vegetarian"
    assert map_diet("mit_meat") is None
    assert map_diet(None) is None


# TC-API-42
@pytest.mark.asyncio
async def test_arma_url_con_canonicos_dieta_y_api_key():
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return ok_response([SAMPLE_RESULT])

    client = client_with_handler(handler)
    result = await client.search(["lentils", "onion"], "vegan")

    assert len(calls) == 1
    url = calls[0].url
    assert url.host == "api.spoonacular.com"
    params = httpx.QueryParams(url.query)
    assert params["includeIngredients"] == "lentils,onion"
    assert params["diet"] == "vegan"
    assert params["apiKey"] == "key"
    assert result[0].id == 715415
    assert result[0].matched_count == 3
    assert result[0].missing_count == 2
    assert result[0].source == "spoonacular"


# TC-API-42b: regresión del bug "vegan con salchichas"
@pytest.mark.asyncio
async def test_diet_vegan_siempre_va_en_la_url():
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return ok_response([])

    client = client_with_handler(handler)
    await client.search(["potato"], "vegan")
    assert httpx.QueryParams(calls[0].url.query)["diet"] == "vegan"


# TC-API-43: caché por ingredientes+dieta
@pytest.mark.asyncio
async def test_cachea_por_ingredientes_y_dieta():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return ok_response([SAMPLE_RESULT])

    client = client_with_handler(handler)
    await client.search(["potato"], "vegan")
    await client.search(["potato"], "vegan")
    assert calls == 1

    await client.search(["potato"], "vegetarian")  # otra dieta = otra entrada
    assert calls == 2


# TC-API-44
@pytest.mark.asyncio
async def test_402_lanza_error_de_cupo_agotado():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(402, json={})

    client = client_with_handler(handler)
    with pytest.raises(RuntimeError, match="daily quota"):
        await client.search(["potato"])


# TC-API-45
@pytest.mark.asyncio
async def test_sin_ingredientes_no_llama_a_la_red():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return ok_response([])

    client = client_with_handler(handler)
    assert await client.search([]) == []
    assert calls == 0


SAMPLE_DETAIL = {
    "id": 715415,
    "title": "Red Lentil Soup",
    "image": "https://img.spoonacular.com/recipes/715415-312x231.jpg",
    "servings": 4,
    "readyInMinutes": 30,
    "sourceUrl": "https://example.com/red-lentil-soup",
    "analyzedInstructions": [
        {"steps": [{"step": "Chop the onion."}, {"step": "Simmer everything for 20 minutes."}]}
    ],
    "extendedIngredients": [
        {"name": "lentils", "original": "2 cups red lentils"},
        {"name": "onion", "original": "1 onion, diced"},
    ],
}


# TC-API-49
@pytest.mark.asyncio
async def test_get_recipe_detail_mapea_ingredientes_y_pasos():
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=SAMPLE_DETAIL)

    client = client_with_handler(handler, api_key="test-key")
    result = await client.get_recipe_detail(715415)

    assert len(calls) == 1
    assert calls[0].url.path == "/recipes/715415/information"
    assert httpx.QueryParams(calls[0].url.query)["apiKey"] == "test-key"
    assert result.title == "Red Lentil Soup"
    assert result.ingredients == [
        {"name": "lentils", "original": "2 cups red lentils"},
        {"name": "onion", "original": "1 onion, diced"},
    ]
    assert result.instructions == ["Chop the onion.", "Simmer everything for 20 minutes."]


# TC-API-50
@pytest.mark.asyncio
async def test_sin_analyzed_instructions_usa_html_plano():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": 1,
                "title": "Simple Dish",
                "instructions": "<ol><li>Boil water.</li><li>Add pasta.</li></ol>",
            },
        )

    client = client_with_handler(handler)
    result = await client.get_recipe_detail(1)
    assert result.instructions == ["Boil water. Add pasta."]
    assert result.ingredients == []


# TC-API-51
@pytest.mark.asyncio
async def test_get_recipe_detail_cachea_por_id():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=SAMPLE_DETAIL)

    client = client_with_handler(handler)
    await client.get_recipe_detail(715415)
    await client.get_recipe_detail(715415)
    assert calls == 1


# TC-API-52
@pytest.mark.asyncio
async def test_404_receta_inexistente():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={})

    client = client_with_handler(handler)
    with pytest.raises(RuntimeError, match="(?i)not found"):
        await client.get_recipe_detail(999999)


# TC-API-53
@pytest.mark.asyncio
async def test_402_en_detail_tambien_cupo_agotado():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(402, json={})

    client = client_with_handler(handler)
    with pytest.raises(RuntimeError, match="daily quota"):
        await client.get_recipe_detail(1)


# --- POST /api/suggestions con catálogo externo ---


@pytest.fixture()
def db():
    database = create_db(":memory:")
    yield database
    database.close()


# TC-API-46
def test_incluye_external_junto_a_sugerencias_locales(db):
    def handler(request: httpx.Request) -> httpx.Response:
        return ok_response([SAMPLE_RESULT])

    app = create_app(db, spoonacular=client_with_handler(handler))
    res = TestClient(app).post(
        "/api/suggestions", json={"ingredients": ["linsen", "zwiebel"], "diet": "vegan"}
    )

    assert res.status_code == 200
    body = res.json()
    assert len(body["suggestions"]) > 0
    assert len(body["external"]) == 1
    assert body["external"][0]["source"] == "spoonacular"


# TC-API-47: resiliencia
def test_si_externo_falla_responde_200_con_local_y_external_error(db):
    def handler(request: httpx.Request) -> httpx.Response:
        raise RuntimeError("network down")

    app = create_app(db, spoonacular=client_with_handler(handler))
    res = TestClient(app).post("/api/suggestions", json={"ingredients": ["potato", "salt"]})

    assert res.status_code == 200
    body = res.json()
    assert len(body["suggestions"]) > 0
    assert body["externalError"] == "network down"
    assert "external" not in body


# TC-API-48
def test_sin_cliente_configurado_no_hay_external(db):
    app = create_app(db)
    res = TestClient(app).post("/api/suggestions", json={"ingredients": ["potato"]})

    assert res.status_code == 200
    body = res.json()
    assert "external" not in body
    assert "externalError" not in body
