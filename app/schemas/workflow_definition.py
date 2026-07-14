from datetime import datetime
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from app.common.job_enums import JobExecutionMode


ALLOWED_WORKFLOW_EXECUTION_MODES = {
    JobExecutionMode.COMFYUI_LOCAL,
    JobExecutionMode.RUNPOD_SERVERLESS,
}


class WorkflowDefinitionCreate(BaseModel):
    key: str = Field(
        min_length=2,
        max_length=150,
        pattern=r"^[a-z0-9][a-z0-9._-]*$",
    )

    name: str = Field(
        min_length=2,
        max_length=255,
    )

    description: str | None = None

    version: int = Field(
        default=1,
        ge=1,
    )

    category: str = Field(
        default="tryon",
        min_length=2,
        max_length=100,
    )

    workflow: dict[str, Any]

    parameter_schema: dict[str, Any] = Field(
        default_factory=dict,
    )

    execution_modes: list[JobExecutionMode] = Field(
        min_length=1,
    )

    metadata: dict[str, Any] = Field(
        default_factory=dict,
    )

    is_active: bool = True
    is_default: bool = False

    @field_validator("execution_modes")
    @classmethod
    def validate_execution_modes(
        cls,
        value: list[JobExecutionMode],
    ) -> list[JobExecutionMode]:
        invalid = [
            item
            for item in value
            if item not in ALLOWED_WORKFLOW_EXECUTION_MODES
        ]

        if invalid:
            raise ValueError(
                "Workflows only support comfyui_local "
                "and runpod_serverless execution modes."
            )

        if len(value) != len(set(value)):
            raise ValueError(
                "Duplicate execution modes are not allowed."
            )

        return value


class WorkflowDefinitionUpdate(BaseModel):
    name: str | None = Field(
        default=None,
        min_length=2,
        max_length=255,
    )

    description: str | None = None

    category: str | None = Field(
        default=None,
        min_length=2,
        max_length=100,
    )

    workflow: dict[str, Any] | None = None

    parameter_schema: dict[str, Any] | None = None

    execution_modes: list[JobExecutionMode] | None = None

    metadata: dict[str, Any] | None = None

    is_active: bool | None = None
    is_default: bool | None = None

    @field_validator("execution_modes")
    @classmethod
    def validate_execution_modes(
        cls,
        value: list[JobExecutionMode] | None,
    ):
        if value is None:
            return value

        invalid = [
            item
            for item in value
            if item not in ALLOWED_WORKFLOW_EXECUTION_MODES
        ]

        if invalid:
            raise ValueError(
                "Workflows only support comfyui_local "
                "and runpod_serverless execution modes."
            )

        if len(value) != len(set(value)):
            raise ValueError(
                "Duplicate execution modes are not allowed."
            )

        return value


class WorkflowDefinitionResponse(BaseModel):
    id: int
    key: str
    name: str
    description: str | None
    version: int
    category: str

    workflow: dict[str, Any]
    parameter_schema: dict[str, Any]
    execution_modes: list[JobExecutionMode]
    metadata: dict[str, Any]

    is_active: bool
    is_default: bool

    created_by_user_id: int | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True
    )


class WorkflowDefinitionListResponse(BaseModel):
    items: list[WorkflowDefinitionResponse]
    total: int
    skip: int
    limit: int


class WorkflowVersionCreate(BaseModel):
    name: str | None = Field(
        default=None,
        min_length=2,
        max_length=255,
    )

    description: str | None = None

    workflow: dict[str, Any]

    parameter_schema: dict[str, Any] = Field(
        default_factory=dict,
    )

    execution_modes: list[JobExecutionMode]

    metadata: dict[str, Any] = Field(
        default_factory=dict,
    )

    activate_new_version: bool = True
    make_default: bool = False