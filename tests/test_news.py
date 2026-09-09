import httpx
import pytest
from fastapi.testclient import TestClient

from app.db import create_db
from app.main import create_app
from app.news import NewsDataClient

SAMPLE_ARTICLE = {
    "article_id": "abc123",
    "title": "10 cozy winter soups",
    "link": "https://example.com/soups",
    "description": "Warm up with these recipes.",
    "image_url": "https://example.com/soup.jpg",
    "source_name": "Food Weekly",
    "pubDate": "2026-07-06 10:00:00",
}


def client_with_handler(handler, api_key="key", ttl_seconds=60 * 60) -> NewsDataClient:
    transport = httpx.MockTransport(handler)
    return NewsDataClient(
        api_key, client=httpx.AsyncClient(transport=transport), ttl_seconds=ttl_seconds
    )


def ok_response(results: list) -> httpx.Response:
    return httpx.Response(200, json={"results": results})


# TC-NEWS-01
@pytest.mark.asyncio
async def test_arma_url_con_categoria_idiomas_y_api_key():
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return ok_response([SAMPLE_ARTICLE])

    client = client_with_handler(handler, api_key="test-key")
    articles = await client.get_news("food")

    assert len(calls) == 1
    url = calls[0].url
    assert url.host == "newsdata.io"
    params = httpx.QueryParams(url.query)
    assert params["category"] == "food"
    assert params["language"] == "en,de"
    assert params["apikey"] == "test-key"
    assert len(articles) == 1
    assert articles[0].id == "abc123"
    assert articles[0].title == "10 cozy winter soups"
    assert articles[0].source == "Food Weekly"


# TC-NEWS-02
@pytest.mark.asyncio
async def test_filtra_resultados_sin_title_o_link():
    def handler(request: httpx.Request) -> httpx.Response:
        return ok_response(
            [SAMPLE_ARTICLE, {"title": "sin link"}, {"link": "https://x.com/sin-titulo"}]
        )

    client = client_with_handler(handler)
    articles = await client.get_news("food")
    assert len(articles) == 1


# TC-NEWS-03
@pytest.mark.asyncio
async def test_cachea_por_topico():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return ok_response([SAMPLE_ARTICLE])

    client = client_with_handler(handler)
    await client.get_news("food")
    await client.get_news("food")
    assert calls == 1

    await client.get_news("health")  # otro tópico = otra entrada de caché
    assert calls == 2


# TC-NEWS-04: fallback a caché vencida
@pytest.mark.asyncio
async def test_si_falla_y_hay_cache_vieja_devuelve_la_cache():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return ok_response([SAMPLE_ARTICLE])
        raise RuntimeError("network down")

    # ttl = 0 -> la caché expira inmediatamente y fuerza el refetch
    client = client_with_handler(handler, ttl_seconds=0)

    first = await client.get_news("food")
    second = await client.get_news("food")  # la red falla, pero hay caché vieja
    assert second == first
    assert calls == 2


# TC-NEWS-05: sin caché previa, el error se propaga
@pytest.mark.asyncio
async def test_sin_cache_previa_propaga_el_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise RuntimeError("network down")

    client = client_with_handler(handler)
    with pytest.raises(RuntimeError, match="network down"):
        await client.get_news("food")


# TC-NEWS-06
@pytest.mark.asyncio
async def test_429_lanza_error_de_cupo_agotado():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={})

    client = client_with_handler(handler)
    with pytest.raises(RuntimeError, match="daily quota"):
        await client.get_news("food")


# --- GET /api/news ---


@pytest.fixture()
def db():
    database = create_db(":memory:")
    yield database
    database.close()


# TC-NEWS-07
def test_devuelve_articles_con_topic_default_food(db):
    def handler(request: httpx.Request) -> httpx.Response:
        return ok_response([SAMPLE_ARTICLE])

    app = create_app(db, news=client_with_handler(handler))
    res = TestClient(app).get("/api/news")
    assert res.status_code == 200
    articles = res.json()["articles"]
    assert len(articles) == 1
    assert articles[0]["title"] == "10 cozy winter soups"


# TC-NEWS-08
def test_topic_invalido_responde_400(db):
    def handler(request: httpx.Request) -> httpx.Response:
        return ok_response([])

    app = create_app(db, news=client_with_handler(handler))
    res = TestClient(app).get("/api/news?topic=sports")
    assert res.status_code == 400
    assert "topic must be one of" in res.json()["error"]


# TC-NEWS-09
def test_sin_cliente_configurado_503(db):
    app = create_app(db)
    res = TestClient(app).get("/api/news")
    assert res.status_code == 503
    assert "not configured" in res.json()["error"]


# TC-NEWS-10
def test_si_la_fuente_falla_responde_502(db):
    def handler(request: httpx.Request) -> httpx.Response:
        raise RuntimeError("network down")

    app = create_app(db, news=client_with_handler(handler))
    res = TestClient(app).get("/api/news?topic=health")
    assert res.status_code == 502
    assert res.json()["error"] == "network down"
