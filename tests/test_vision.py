import base64
import json
import shutil
import subprocess

import httpx
import pytest

from worker.extract import ExtractionError
from worker.vision import ImageError, describe, normalize


def vision_llm(content: str, seen: list[dict]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    return httpx.MockTransport(handler)


def answer(**overrides) -> str:
    item = {"raw_text": "blanc de poulet grillé", "query": "poulet", "quantity": 150, "unit": "g", "cooking_method": "grilled"}
    return json.dumps({"description": "Poulet et riz.", "items": [item | overrides]})


async def test_the_photo_is_sent_as_a_jpeg_data_url_to_the_vision_model(settings):
    settings.vision_model = "vision-model"
    requests: list[dict] = []
    description, extraction = await describe(b"\xff\xd8jpeg", settings, vision_llm(answer(), requests))

    (body,) = requests
    assert body["model"] == "vision-model" and body["temperature"] == 0
    assert body["response_format"]["json_schema"]["name"] == "meal_photo"
    image = body["messages"][1]["content"][1]["image_url"]["url"]
    assert image == "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8jpeg").decode()
    assert "French" in body["messages"][0]["content"]
    assert description == "Poulet et riz."
    assert extraction.language == "fr" and extraction.items[0].cooking_method == "grilled"


async def test_without_a_vision_model_the_text_model_is_used(settings):
    requests: list[dict] = []
    await describe(b"x", settings, vision_llm(answer(), requests))
    assert requests[0]["model"] == settings.llm_model


async def test_the_query_language_comes_from_the_settings(settings):
    settings.vision_language = "en"
    requests: list[dict] = []
    _, extraction = await describe(b"x", settings, vision_llm(answer(), requests))
    assert extraction.language == "en" and "English" in requests[0]["messages"][0]["content"]


@pytest.mark.parametrize("overrides", [{"quantity": -1}, {"cooking_method": "smoked"}, {"unit": "kg"}])
async def test_bad_vision_output_is_rejected(settings, overrides):
    with pytest.raises(ExtractionError):
        await describe(b"x", settings, vision_llm(answer(**overrides), []))


async def test_vision_item_count_is_capped(settings):
    settings.max_items = 2
    item = {"raw_text": "a", "query": "a", "quantity": None, "unit": None, "cooking_method": None}
    content = json.dumps({"description": "", "items": [item] * 5})
    _, extraction = await describe(b"x", settings, vision_llm(content, []))
    assert len(extraction.items) == 2


needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


@needs_ffmpeg
async def test_normalize_bounds_the_size_and_outputs_jpeg(settings, tmp_path):
    png = tmp_path / "big.png"
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "color=red:s=3000x2000", "-frames:v", "1", str(png)],
        check=True,
    )
    settings.max_image_px = 300
    jpeg = await normalize(png.read_bytes(), settings)
    assert jpeg[:2] == b"\xff\xd8"
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=width,height", "-of", "csv=p=0", "-"],
        input=jpeg, capture_output=True, check=True,
    )
    assert probe.stdout.decode().strip() == "300,200"


@needs_ffmpeg
async def test_normalize_rejects_garbage(settings):
    with pytest.raises(ImageError):
        await normalize(b"definitely not an image", settings)
