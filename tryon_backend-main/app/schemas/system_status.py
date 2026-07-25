from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SystemStatusUpdate(BaseModel):
    maintenance_mode: bool | None = None
    registration_enabled: bool | None = None
    tryon_enabled: bool | None = None
    public_message: str | None = None
    internal_message: str | None = None


class SystemStatusResponse(BaseModel):
    id: int
    maintenance_mode: bool
    registration_enabled: bool
    tryon_enabled: bool
    public_message: str | None
    internal_message: str | None
    updated_by_user_id: int | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PublicSystemStatusResponse(BaseModel):
    maintenance_mode: bool
    registration_enabled: bool
    tryon_enabled: bool
    public_message: str | None