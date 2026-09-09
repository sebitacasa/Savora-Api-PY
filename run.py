"""
Bootstrap del servidor: carga variables de entorno, arma la DB y los
clientes externos, y levanta uvicorn. Equivalente a src/server.ts.

Variables de entorno locales (api key de Spoonacular, etc.). El archivo
.env no se commitea; ver .env.example.
"""

import os

import uvicorn
from anthropic import AsyncAnthropic
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

from app.db import create_db  # noqa: E402  (después de load_dotenv a propósito)
from app.main import create_app  # noqa: E402
from app.news import NewsDataClient  # noqa: E402
from app.spoonacular import SpoonacularClient  # noqa: E402

PORT = int(os.environ.get("PORT", "3000"))
DB_FILE = os.environ.get("DB_FILE", os.path.join(BASE_DIR, "data", "nicy.db"))

db = create_db(DB_FILE)

spoonacular_key = os.environ.get("SPOONACULAR_API_KEY")
news_key = os.environ.get("NEWSDATA_API_KEY")
anthropic_key = os.environ.get("ANTHROPIC_API_KEY")

app = create_app(
    db,
    spoonacular=SpoonacularClient(spoonacular_key) if spoonacular_key else None,
    news=NewsDataClient(news_key) if news_key else None,
    assistant=AsyncAnthropic(api_key=anthropic_key) if anthropic_key else None,
)


if __name__ == "__main__":
    print(f"Nicy Kitchen API (Python) escuchando en http://localhost:{PORT}")
    print(
        "Catálogo externo: Spoonacular activado."
        if spoonacular_key
        else "Catálogo externo: desactivado (definí SPOONACULAR_API_KEY en .env para activarlo)."
    )
    print(
        "Noticias: NewsData activado."
        if news_key
        else "Noticias: desactivado (definí NEWSDATA_API_KEY en .env para activarlo)."
    )
    print(
        "Wooly (asistente IA): activado."
        if anthropic_key
        else "Wooly (asistente IA): desactivado (definí ANTHROPIC_API_KEY en .env para activarlo)."
    )
    uvicorn.run(app, host="0.0.0.0", port=PORT)
