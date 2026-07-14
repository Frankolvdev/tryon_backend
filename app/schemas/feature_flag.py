from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FeatureFlagCreate(BaseModel):
    key: str
    name: str
    description: str | None = None
    is_enabled: bool = False
    is_public: bool = True


class FeatureFlagUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    is_enabled: bool | None = None
    is_public: bool | None = None


class FeatureFlagResponse(BaseModel):
    id: int
    key: str
    name: str
    description: str | None
    is_enabled: bool
    is_public: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PublicFeatureFlagsResponse(BaseModel):
    flags: dict[str, bool]