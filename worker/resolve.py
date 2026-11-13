"""Turn ingredient names into ranked candidates with the public ingredient search."""

import httpx

from worker.config import Settings
from worker.schemas import Candidate, ExtractedItem, Extraction

# The search endpoint ranks but does not score, so the score is derived from the rank.
RANK_STEP = 0.12


async def _candidates(
    client: httpx.AsyncClient, query: str, lang: str, settings: Settings
) -> list[Candidate]:
    resp = await client.get(
        "/ingredients/search",
        params={"q": query, "lang": lang, "limit": settings.candidates_per_item},
    )
    resp.raise_for_status()
    return [
        Candidate(ingredient_id=hit["ingredientId"], name=hit["label"], score=round(max(0.1, 0.95 - RANK_STEP * rank), 2))
        for rank, hit in enumerate(resp.json()[: settings.candidates_per_item])
    ]


async def resolve(
    extraction: Extraction, settings: Settings, transport: httpx.AsyncBaseTransport | None = None
) -> list[ExtractedItem]:
    async with httpx.AsyncClient(
        base_url=settings.api_url.rstrip("/"), timeout=15, follow_redirects=False, transport=transport
    ) as client:
        items = []
        for spoken in extraction.items:
            candidates = await _candidates(client, spoken.query, extraction.language, settings)
            items.append(
                ExtractedItem(
                    raw_text=spoken.raw_text,
                    quantity=spoken.quantity,
                    unit=spoken.unit,
                    cooking_method=spoken.cooking_method,
                    candidates=candidates,
                )
            )
    return items
