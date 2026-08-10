from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SexName = Literal["woman", "man"]

DEFAULT_LIMITS = {
    "hips_min": 0.0,
    "hips_max": 9.0,
    "breasts_min": None,
    "breasts_max": 1.5,
    "fat_thin_min": -1.5,
    "fat_thin_max": 1.8,
    "skin_tone_min": -5.0,
    "skin_tone_max": 5.0,
}

DEFAULT_FORMULA = {
    "fat_step": 0.0,
    "hips_step": 0.0,
    "breasts_step": 0.0,
    "fat_to_hips": 0.0,
    "fat_to_breasts": 0.0,
    "hips_to_breasts": 0.0,
}

DEFAULT_FIXED_VALUES = {
    "skin_tone": 0.0,
    "hair_length": 0.0,
}


class BodyProportionWorkflowConfigUpsert(BaseModel):
    workflow: dict[str, Any] | None = None
    input_mapping: dict[str, dict[str, str]] = Field(default_factory=dict)
    limits: dict[str, float | None] = Field(default_factory=lambda: dict(DEFAULT_LIMITS))
    formula: dict[str, float] = Field(default_factory=lambda: dict(DEFAULT_FORMULA))
    fixed_values: dict[str, float] = Field(default_factory=lambda: dict(DEFAULT_FIXED_VALUES))
    is_enabled: bool = False
    notes: str | None = None


class BodyProportionWorkflowConfigResponse(BaseModel):
    id: int | None = None
    sex: SexName
    workflow: dict[str, Any] | None = None
    input_mapping: dict[str, dict[str, str]]
    limits: dict[str, float | None]
    formula: dict[str, float]
    fixed_values: dict[str, float]
    is_enabled: bool
    notes: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class BodyProportionPresetCreate(BaseModel):
    sex: SexName = "woman"
    sort_order: float | None = None
    display_name: str | None = Field(default=None, max_length=180)
    hips_size: float
    fat_thin: float
    breasts_size: float
    skin_tone: float | None = None
    hair_length: float | None = None


class BodyProportionPresetUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=180)
    sort_order: float | None = None
    hips_size: float | None = None
    fat_thin: float | None = None
    breasts_size: float | None = None
    skin_tone: float | None = None
    hair_length: float | None = None


class BodyProportionNextRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=180)


class BodyProportionInterpolateRequest(BaseModel):
    before_id: int
    after_id: int
    ratio: float = Field(default=0.5, gt=0.0, lt=1.0)
    display_name: str | None = Field(default=None, max_length=180)


class BodyProportionPresetResponse(BaseModel):
    id: int
    sex: SexName
    sort_order: float
    profile_key: str
    display_name: str
    category_slug: str
    hips_size: float
    fat_thin: float
    breasts_size: float
    skin_tone: float
    hair_length: float
    image_storage_file_id: int | None
    image_url: str | None = None
    local_mirror_path: str | None
    status: str
    last_error: str | None
    generation_metadata: dict[str, Any]
    generated_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BodyProportionPresetListResponse(BaseModel):
    items: list[BodyProportionPresetResponse]
    total: int


class BodyProportionGenerationResponse(BaseModel):
    preset: BodyProportionPresetResponse
    prompt_id: str
    storage_provider: str
    overwritten: bool


class BodyProportionHealthResponse(BaseModel):
    local_only: bool = True
    comfyui: dict[str, Any]
