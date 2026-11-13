import json

import httpx
import pytest

from worker.extract import ExtractionError, extract
from worker.resolve import resolve
from worker.schemas import Extraction, SpokenItem
from worker.stt import TranscriptionError, parse_handy_output


def llm(content: str, status: int = 200) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["response_format"]["type"] == "json_schema" and body["temperature"] == 0
        return httpx.Response(status, json={"choices": [{"message": {"content": content}}]})

    return httpx.MockTransport(handler)


async def test_extraction_is_parsed_and_validated(settings):
    content = json.dumps(
        {
            "language": "fr",
            "items": [
                {"raw_text": "deux oeufs au plat", "query": "oeuf", "quantity": 2, "unit": "piece", "cooking_method": "fried"}
            ],
        }
    )
    result = await extract("deux oeufs au plat", settings, llm(content))
    assert result.items[0].query == "oeuf" and result.items[0].cooking_method == "fried"


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        json.dumps({"language": "fr", "items": [{"raw_text": "x", "query": "y", "cooking_method": "deep-fried-in-lava"}]}),
        json.dumps({"language": "fr", "items": [{"raw_text": "x", "query": "y", "quantity": -3}]}),
        json.dumps({"language": "fr", "items": [{"raw_text": "x", "query": "y", "quantity": 1e9}]}),
        json.dumps({"language": "de", "items": []}),
    ],
)
async def test_bad_model_output_is_rejected(settings, content):
    with pytest.raises(ExtractionError):
        await extract("x", settings, llm(content))


async def test_llm_http_error_is_an_extraction_error(settings):
    with pytest.raises(ExtractionError):
        await extract("x", settings, llm("{}", status=500))


async def test_item_count_is_capped(settings):
    settings.max_items = 2
    items = [{"raw_text": "a", "query": "a"}] * 5
    result = await extract("a", settings, llm(json.dumps({"language": "en", "items": items})))
    assert len(result.items) == 2


async def test_candidates_come_from_the_search_with_rank_based_scores(settings):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/ingredients/search"
        assert request.url.params["q"] == "riz basmati" and request.url.params["lang"] == "fr"
        return httpx.Response(
            200,
            json=[
                {"ingredientId": "riz_basmati_cuit", "label": "Basmati rice, cooked"},
                {"ingredientId": "riz_basmati_cru", "label": "Basmati rice, raw"},
            ],
        )

    extraction = Extraction(language="fr", items=[SpokenItem(raw_text="150 g de riz basmati", query="riz basmati", quantity=150, unit="g")])
    (item,) = await resolve(extraction, settings, httpx.MockTransport(handler))
    assert [c.ingredient_id for c in item.candidates] == ["riz_basmati_cuit", "riz_basmati_cru"]
    assert item.candidates[0].score > item.candidates[1].score
    assert item.quantity == 150 and item.unit == "g"


def test_handy_result_is_the_last_json_line_among_log_noise():
    out = b'[INFO] loading\n{"not": "this"}\n{"text":" deux oeufs ","rtf":4.6}\n'
    assert parse_handy_output(out) == "deux oeufs"


@pytest.mark.parametrize("out", [b"", b"[INFO] only logs\n", b"{broken"])
def test_handy_without_a_result_raises(out):
    with pytest.raises(TranscriptionError):
        parse_handy_output(out)
