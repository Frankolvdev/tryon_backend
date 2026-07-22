from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.common.enums import StorageProvider


class StorageFileResponse(BaseModel):
    id: int
    user_id: int | None
    user_email: str | None = None
    user_full_name: str | None = None
    user_role: str | None = None
    provider: StorageProvider
    bucket: str | None
    object_key: str
    public_url: str | None
    original_filename: str | None
    content_type: str | None
    size_bytes: int | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
