import httpx
import pytest
from fastapi.testclient import TestClient

from app.assistant import ask_wooly
from app.db import create_db
from app.main import create_app
from app.spoonacular import SpoonacularClient


class FakeTextBlock:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class FakeToolUseBlock:
    def __init__(self, id_, name, input_):
        self.type = "tool_use"
        self.id = id_
        self.name = name
        self.input = input_


class FakeResponse:
    def __init__(self, stop_reason, content):
        self.stop_reason = stop_reason
        self.content = content


class FakeMessages:
    def __init__(self, responses):
        self._responses = iter(responses)
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return next(self._responses)


class FakeAnthropic:
    def __init__(self, responses):
        self.messages = FakeMessages(responses)


def spoonacular_with_handler(handler) -> SpoonacularClient:
    transport = httpx.MockTransport(handler)
    return SpoonacularClient("key", client=httpx.AsyncClient(transport=transport))


@pytest.fixture()
def db():
    database = create_db(":memory:")
    yield database
    database.close()


@pytest.mark.asyncio
async def test_ask_wooly_responde_directo_sin_usar_herramientas(db):
    client = FakeAnthropic(
        [FakeResponse("end_turn", [FakeTextBlock("Baa! Ask me about ingredients!")])]
    )

    result = await ask_wooly(client, db, "hi there")

    assert result["reply"] == "Baa! Ask me about ingredients!"
    assert result["recipes"] == []
    assert result["externalRecipes"] == []
    assert result["history"] == [
        {"role": "user", "content": "hi there"},
        {"role": "assistant", "content": "Baa! Ask me about ingredients!"},
    ]
    assert len(client.messages.calls) == 1
    # Sin spoonacular configurado, ni se ofrece la herramienta
    assert len(client.messages.calls[0]["tools"]) == 1


@pytest.mark.asyncio
async def test_ask_wooly_usa_search_recipes_y_devuelve_matches_reales(db):
    tool_call = FakeToolUseBlock("tool_1", "search_recipes", {"ingredients": ["potato", "salt"]})
    client = FakeAnthropic(
        [
            FakeResponse("tool_use", [tool_call]),
            FakeResponse(
                "end_turn",
                [FakeTextBlock("Try Mashed Potatoes, it only needs what you've got!")],
            ),
        ]
    )

    result = await ask_wooly(client, db, "I have potato and salt")

    assert result["reply"] == "Try Mashed Potatoes, it only needs what you've got!"
    assert len(result["recipes"]) > 0
    assert result["recipes"][0]["source"] == "local"
    assert "matched" in result["recipes"][0]
    # No debe filtrarse ningún detalle de tool use al historial expuesto al cliente
    assert result["history"] == [
        {"role": "user", "content": "I have potato and salt"},
        {
            "role": "assistant",
            "content": "Try Mashed Potatoes, it only needs what you've got!",
        },
    ]
    second_call_messages = client.messages.calls[1]["messages"]
    assert second_call_messages[-1]["content"][0]["type"] == "tool_result"
    assert second_call_messages[-1]["content"][0]["tool_use_id"] == "tool_1"


@pytest.mark.asyncio
async def test_ask_wooly_usa_spoonacular_cuando_el_modelo_lo_pide(db):
    tool_call = FakeToolUseBlock(
        "tool_2", "search_spoonacular_recipes", {"ingredients": ["lentils"]}
    )
    client = FakeAnthropic(
        [
            FakeResponse("tool_use", [tool_call]),
            FakeResponse("end_turn", [FakeTextBlock("Found something online for you!")]),
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": 999,
                        "title": "Red Lentil Soup",
                        "image": "https://img.spoonacular.com/x.jpg",
                        "usedIngredientCount": 1,
                        "missedIngredientCount": 3,
                    }
                ]
            },
        )

    spoonacular = spoonacular_with_handler(handler)
    result = await ask_wooly(client, db, "give me something online", spoonacular=spoonacular)

    assert result["reply"] == "Found something online for you!"
    assert result["recipes"] == []
    assert len(result["externalRecipes"]) == 1
    assert result["externalRecipes"][0]["source"] == "spoonacular"
    assert result["externalRecipes"][0]["title"] == "Red Lentil Soup"
    # La herramienta de spoonacular se ofrece cuando hay cliente configurado
    assert len(client.messages.calls[0]["tools"]) == 2


@pytest.mark.asyncio
async def test_sin_spoonacular_configurado_no_se_ofrece_la_herramienta(db):
    client = FakeAnthropic([FakeResponse("end_turn", [FakeTextBlock("hi")])])
    await ask_wooly(client, db, "hi", spoonacular=None)
    tool_names = [t["name"] for t in client.messages.calls[0]["tools"]]
    assert "search_spoonacular_recipes" not in tool_names


@pytest.mark.asyncio
async def test_ask_wooly_mantiene_el_historial_previo(db):
    client = FakeAnthropic([FakeResponse("end_turn", [FakeTextBlock("Sure, another idea!")])])
    previous_history = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "Baa! Hi there!"},
    ]

    result = await ask_wooly(client, db, "give me another idea", previous_history)

    assert result["history"][:2] == previous_history
    assert result["history"][-2:] == [
        {"role": "user", "content": "give me another idea"},
        {"role": "assistant", "content": "Sure, another idea!"},
    ]
    sent_messages = client.messages.calls[0]["messages"]
    assert sent_messages[0] == previous_history[0]


# --- POST /api/assistant ---


def test_sin_assistant_configurado_503(db):
    app = create_app(db)
    res = TestClient(app).post("/api/assistant", json={"message": "hi"})
    assert res.status_code == 503
    assert "not configured" in res.json()["error"]


def test_sin_message_400(db):
    fake = FakeAnthropic([FakeResponse("end_turn", [FakeTextBlock("hi")])])
    app = create_app(db, assistant=fake)
    res = TestClient(app).post("/api/assistant", json={})
    assert res.status_code == 400
    assert "message is required" in res.json()["error"]


def test_message_vacio_400(db):
    fake = FakeAnthropic([FakeResponse("end_turn", [FakeTextBlock("hi")])])
    app = create_app(db, assistant=fake)
    res = TestClient(app).post("/api/assistant", json={"message": "   "})
    assert res.status_code == 400


def test_history_no_lista_400(db):
    fake = FakeAnthropic([FakeResponse("end_turn", [FakeTextBlock("hi")])])
    app = create_app(db, assistant=fake)
    res = TestClient(app).post(
        "/api/assistant", json={"message": "hi", "history": "not a list"}
    )
    assert res.status_code == 400


def test_caso_feliz_devuelve_reply_e_historial(db):
    fake = FakeAnthropic([FakeResponse("end_turn", [FakeTextBlock("Baa! Hi!")])])
    app = create_app(db, assistant=fake)
    res = TestClient(app).post("/api/assistant", json={"message": "hi"})

    assert res.status_code == 200
    body = res.json()
    assert body["reply"] == "Baa! Hi!"
    assert body["recipes"] == []
    assert body["externalRecipes"] == []
    assert len(body["history"]) == 2


def test_error_del_cliente_responde_502(db):
    class BrokenMessages:
        async def create(self, **kwargs):
            raise RuntimeError("Anthropic is down")

    class BrokenClient:
        messages = BrokenMessages()

    app = create_app(db, assistant=BrokenClient())
    res = TestClient(app).post("/api/assistant", json={"message": "hi"})
    assert res.status_code == 502
    assert res.json()["error"] == "Anthropic is down"
