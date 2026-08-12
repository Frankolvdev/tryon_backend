from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field

SexName = Literal["woman", "man"]

class BodyVariantResponse(BaseModel):
    id: int
    display_name: str
    sex: SexName
    hips_size: float
    fat_thin: float
    breasts_size: float
    skin_tone: float
    hair_length: float
    fat_band: str | None = None
    hips_band: str | None = None
    breast_band: str | None = None
    image_url: str
    sort_order: float

class BodyVariantCatalogResponse(BaseModel):
    items: list[BodyVariantResponse]
    total: int

class BubbleButtVariantResponse(BaseModel):
    id: int
    variant_index: int
    display_name: str
    bubble_butt: float
    image_url: str

class BubbleButtVariantCatalogResponse(BaseModel):
    items: list[BubbleButtVariantResponse]
    total: int

class AiModelProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    sex: SexName = "woman"

class AiModelProfileBodyUpdate(BaseModel):
    body_proportion_preset_id: int

class AiModelProfileResponse(BaseModel):
    id: int
    name: str
    sex: SexName
    body_proportion_preset_id: int | None
    body_image_url: str | None = None
    stage: str
    created_at: datetime
    updated_at: datetime
