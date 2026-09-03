from datetime import datetime

from pydantic import BaseModel, Field


class AuditExportRequest(BaseModel):
    actor_user_id: int | None = None
    actor_email: str | None = None
    actor_type: str | None = None

    action: str | None = None

    entity_type: str | None = None
    entity_id: str | None = None

    success: bool | None = None

    correlation_id: str | None = None
    request_id: str | None = None

    is_restorable: bool | None = None

    search: str | None = None

    created_from: datetime | None = None
    created_to: datetime | None = None

    max_records: int = Field(
        default=10000,
        ge=1,
        le=100000,
    )


class AuditExportMetadata(BaseModel):
    format: str
    filename: str
    exported_records: int
    generated_at: datetime