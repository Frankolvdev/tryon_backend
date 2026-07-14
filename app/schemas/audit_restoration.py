from typing import Any

from pydantic import BaseModel, Field


class AuditRestorePreviewResponse(BaseModel):
    audit_entry_id: int

    entity_type: str
    entity_id: str

    can_restore: bool
    reason: str | None = None

    current_data: dict[str, Any] | None = None
    restore_data: dict[str, Any] | None = None

    changed_fields: list[str] = Field(
        default_factory=list,
    )

    ignored_fields: list[str] = Field(
        default_factory=list,
    )

    missing_fields: list[str] = Field(
        default_factory=list,
    )


class AuditRestoreRequest(BaseModel):
    reason: str = Field(
        min_length=3,
        max_length=5000,
    )

    expected_updated_at: str | None = Field(
        default=None,
        max_length=100,
    )

    restore_null_values: bool = True


class AuditRestoreResponse(BaseModel):
    success: bool

    restored_entity_type: str
    restored_entity_id: str

    source_audit_entry_id: int
    restoration_audit_entry_id: int | None = None

    changed_fields: list[str] = Field(
        default_factory=list,
    )

    ignored_fields: list[str] = Field(
        default_factory=list,
    )

    before_data: dict[str, Any] | None = None
    after_data: dict[str, Any] | None = None

    message: str


class AuditedMutationMetadata(BaseModel):
    module: str | None = None
    reason: str | None = None
    operation_source: str | None = None

    additional_data: dict[str, Any] = Field(
        default_factory=dict,
    )