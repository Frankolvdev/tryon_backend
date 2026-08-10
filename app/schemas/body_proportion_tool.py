from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SexName = Literal["woman", "man"]
StorageMode = Literal["auto", "local", "amazon_s3", "cloudflare_r2"]

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

# Low-fat values are calibrated from the 13 presets supplied by the user.
# Medium/high-fat compensation values are intentionally editable starting points.
DEFAULT_FORMULA: dict[str, Any] = {
    "fat_levels": {
        "low": {"label": "Low Fat", "fat_thin": 1.0, "hips_compensation": 0.0, "breasts_compensation": 0.0},
        "medium": {"label": "Medium Fat", "fat_thin": 0.0, "hips_compensation": 0.0, "breasts_compensation": 0.0},
        "high": {"label": "High Fat", "fat_thin": -1.0, "hips_compensation": 0.0, "breasts_compensation": 0.0},
    },
    "ass_levels": {
        "small": {"label": "Small Ass", "hips_size": 0.0},
        "medium": {"label": "Medium Ass", "hips_size": 3.0},
        "big": {"label": "Big Ass", "hips_size": 6.0},
        "huge": {"label": "Huge Ass", "hips_size": 7.0},
    },
    "breast_levels": {
        "small": {"label": "Small Breast", "base": 0.0},
        "medium": {"label": "Medium Breast", "base": 0.5},
        "big": {"label": "Big Breast", "base": 1.0},
        "huge": {"label": "Huge Breast", "base": 1.5},
    },
    "ass_breast_compensation": {
        "small": {"small": 0.0, "medium": 0.0, "big": 0.0, "huge": 0.0},
        "medium": {"small": 0.0, "medium": -0.2, "big": -0.2, "huge": -0.2},
        "big": {"small": -0.2, "medium": -0.4, "big": -0.4, "huge": -0.4},
        "huge": {"small": -0.2, "medium": -0.4, "big": -0.4, "huge": -0.4},
    },
}

DEFAULT_FIXED_VALUES = {
    "skin_tone": 3.0,
    "hair_length": 3.5,
}


class BodyProportionWorkflowConfigUpsert(BaseModel):
    workflow: dict[str, Any] | None = None
    input_mapping: dict[str, dict[str, str]] = Field(default_factory=dict)
    limits: dict[str, float | None] = Field(default_factory=lambda: dict(DEFAULT_LIMITS))
    formula: dict[str, Any] = Field(default_factory=lambda: dict(DEFAULT_FORMULA))
    fixed_values: dict[str, float] = Field(default_factory=lambda: dict(DEFAULT_FIXED_VALUES))
    storage_mode: StorageMode = "auto"
    is_enabled: bool = False
    notes: str | None = None


class BodyProportionWorkflowConfigResponse(BaseModel):
    id: int | None = None
    sex: SexName
    workflow: dict[str, Any] | None = None
    input_mapping: dict[str, dict[str, str]]
    limits: dict[str, float | None]
    formula: dict[str, Any]
    fixed_values: dict[str, float]
    storage_mode: StorageMode
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
    fat_band: str | None = None
    ass_band: str | None = None
    breast_band: str | None = None
    is_base_category: bool = False
    base_category_key: str | None = None


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


class BodyProportionSeedResponse(BaseModel):
    created: int
    existing: int
    total_base: int


class BodyProportionRecalculateRequest(BaseModel):
    include_ready: bool = False


class BodyProportionRecalculateResponse(BaseModel):
    updated: int
    skipped_ready: int


class BodyProportionStorageOptionsResponse(BaseModel):
    active_provider: str
    modes: list[str]


class BodyProportionPresetResponse(BaseModel):
    id: int
    sex: SexName
    sort_order: float
    profile_key: str
    display_name: str
    category_slug: str
    fat_band: str | None = None
    ass_band: str | None = None
    breast_band: str | None = None
    is_base_category: bool = False
    base_category_key: str | None = None
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
