from datetime import datetime
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)


class AuditFieldChange(BaseModel):
    field: str
    change_type: str

    before: Any | None = None
    after: Any | None = None


class AuditEntryCreate(BaseModel):
    actor_user_id: int | None = None

    actor_email: str | None = Field(
        default=None,
        max_length=255,
    )

    actor_type: str = Field(
        default="system",
        min_length=2,
        max_length=30,
    )

    action: str = Field(
        min_length=1,
        max_length=120,
    )

    entity_type: str = Field(
        min_length=1,
        max_length=120,
    )

    entity_id: str | int | None = None

    success: bool = True

    before_data: dict[str, Any] | None = None
    after_data: dict[str, Any] | None = None

    metadata: dict[str, Any] = Field(
        default_factory=dict,
    )

    ip_address: str | None = Field(
        default=None,
        max_length=100,
    )

    user_agent: str | None = None

    correlation_id: str | None = Field(
        default=None,
        max_length=128,
    )

    request_id: str | None = Field(
        default=None,
        max_length=128,
    )

    error_type: str | None = Field(
        default=None,
        max_length=255,
    )

    error_message: str | None = None

    is_restorable: bool = False

    restored_from_entry_id: int | None = None


class AuditEntryResponse(BaseModel):
    id: int

    actor_user_id: int | None
    actor_email: str | None
    actor_type: str

    action: str
    entity_type: str
    entity_id: str | None

    success: bool

    before_data: dict[str, Any] | None
    after_data: dict[str, Any] | None
    diff_data: dict[str, Any] | None
    metadata: dict[str, Any]

    ip_address: str | None
    user_agent: str | None

    correlation_id: str | None
    request_id: str | None

    error_type: str | None
    error_message: str | None

    is_restorable: bool
    restored_from_entry_id: int | None

    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
    )


class AuditEntryListResponse(BaseModel):
    items: list[AuditEntryResponse]

    total: int
    skip: int
    limit: int


class AuditEntityHistoryResponse(BaseModel):
    entity_type: str
    entity_id: str

    items: list[AuditEntryResponse]

    total: int


class AuditDiffResponse(BaseModel):
    before_data: dict[str, Any] | None
    after_data: dict[str, Any] | None

    changes: list[AuditFieldChange]

    added_fields: list[str]
    removed_fields: list[str]
    changed_fields: list[str]

    total_changes: int


class AuditSummaryResponse(BaseModel):
    total_entries: int
    successful_entries: int
    failed_entries: int
    restorable_entries: int

    by_actor_type: dict[str, int]
    by_action: dict[str, int]
    by_entity_type: dict[str, int]

    generated_at: datetime