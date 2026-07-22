from datetime import datetime
from pydantic import BaseModel, Field

class UserLibraryFileResponse(BaseModel):
    id: int
    filename: str
    content_type: str | None
    size_bytes: int
    provider: str
    url: str
    created_at: datetime

class UserLibraryUsageResponse(BaseModel):
    used_bytes: int
    quota_bytes: int
    available_bytes: int
    percent_used: float
    file_count: int

class UserLibraryListResponse(BaseModel):
    items: list[UserLibraryFileResponse]
    usage: UserLibraryUsageResponse

class UserLibraryAdminQuotaUpdate(BaseModel):
    quota_mb: int = Field(ge=1, le=1024 * 1024)
