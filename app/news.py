"""
Cliente de NewsData.io (https://newsdata.io), la fuente de noticias de
comida/salud para la home de la app. Mismo patrón que Spoonacular:
la app nunca habla con NewsData directo — este backend hace de proxy,
la key no viaja al cliente y cacheamos para cuidar el cupo gratuito
(~200 créditos/día).

Decisiones:
 - Caché en memoria de 1 h por tópico: las noticias no cambian minuto a
   minuto y un solo request sirve a todos los usuarios de esa hora.
 - Fallback a caché vencida: si NewsData falla, devolvemos las últimas
   noticias buenas que tengamos (viejas > carrusel vacío).
 - Idiomas: en + de (decisión de producto del resto de la app).
 - Timeout de 5 s para no colgar nuestra respuesta.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Literal, Optional

import httpx

NewsTopic = Literal["food", "health"]
NEWS_TOPICS: tuple[NewsTopic, ...] = ("food", "health")


@dataclass
class NewsArticle:
    id: str
    title: str
    link: str
    description: Optional[str]
    image: Optional[str]
    source: Optional[str]
    published_at: Optional[str]


class NewsDataClient:
    def __init__(
        self,
        api_key: str,
        client: Optional[httpx.AsyncClient] = None,
        ttl_seconds: float = 60 * 60,
        timeout_seconds: float = 5.0,
        languages: str = "en,de",
    ):
        self.api_key = api_key
        self.client = client or httpx.AsyncClient()
        self.ttl_seconds = ttl_seconds
        self.timeout_seconds = timeout_seconds
        self.languages = languages
        self._cache: dict[str, tuple[float, list[NewsArticle]]] = {}

    async def get_news(self, topic: NewsTopic) -> list[NewsArticle]:
        cached = self._cache.get(topic)
        if cached and time.monotonic() - cached[0] < self.ttl_seconds:
            return cached[1]

        try:
            params = {
                "apikey": self.api_key,
                "category": topic,
                "language": self.languages,
                "image": "1",  # solo notas con imagen: la home es visual
            }
            res = await self.client.get(
                "https://newsdata.io/api/1/latest",
                params=params,
                timeout=self.timeout_seconds,
            )

            if res.status_code in (401, 403):
                raise RuntimeError("NewsData API key is invalid.")
            if res.status_code == 429:
                raise RuntimeError("NewsData daily quota exhausted.")
            if res.status_code >= 400:
                raise RuntimeError(f"NewsData responded {res.status_code}.")

            body = res.json()
            data = [
                NewsArticle(
                    id=r.get("article_id") or r["link"],
                    title=r["title"],
                    link=r["link"],
                    description=r.get("description"),
                    image=r.get("image_url"),
                    source=r.get("source_name") or r.get("source_id"),
                    published_at=r.get("pubDate"),
                )
                for r in body.get("results", [])
                if r.get("title") and r.get("link")
            ]

            self._cache[topic] = (time.monotonic(), data)
            return data
        except Exception:
            # Caché vencida como red de seguridad: noticias viejas > carrusel vacío.
            if cached:
                return cached[1]
            raise
