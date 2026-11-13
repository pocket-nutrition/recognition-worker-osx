"""Wire shapes shared with https://github.com/pocket-nutrition/recognition (`app/schemas.py`, `app/worker.py`)."""

from typing import Literal

from pydantic import BaseModel, Field


class Drop(BaseModel):
    url: str
    token: str
    record_id: str
    inbox_public_key: str


class Job(BaseModel):
    lease_id: str
    ticket_id: str
    lease_expires_at: float
    audio_content_type: str
    drop: Drop | None = None


class Candidate(BaseModel):
    ingredient_id: str
    name: str
    score: float


class ExtractedItem(BaseModel):
    raw_text: str
    quantity: float | None = None
    unit: str | None = None
    cooking_method: str | None = None
    candidates: list[Candidate]


class CaptureResult(BaseModel):
    transcript: str
    language: str
    items: list[ExtractedItem]


# What the language model is allowed to say. Everything it returns is validated against this:
# the transcript is user-controlled text, so the model output is never trusted as-is.
CookingMethod = Literal["raw", "boiled", "steamed", "grilled", "fried", "roasted"]


class SpokenItem(BaseModel):
    raw_text: str = Field(min_length=1, max_length=200)
    # Ingredient name as it would be searched, e.g. "riz basmati".
    query: str = Field(min_length=1, max_length=100)
    quantity: float | None = Field(default=None, gt=0, le=10000)
    unit: Literal["g", "ml", "piece"] | None = None
    cooking_method: CookingMethod | None = None


class Extraction(BaseModel):
    language: Literal["fr", "en"] = "fr"
    items: list[SpokenItem]


class SeenMeal(BaseModel):
    """What the vision model may say about a photo. Validated like `Extraction`: the photo is untrusted."""

    description: str = Field(max_length=500)
    items: list[SpokenItem]
