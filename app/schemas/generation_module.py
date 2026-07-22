from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.common.generation_module_enums import (
    GenerationExecutionEngine,
    GenerationModuleInputType,
    GenerationModuleOutputType,
    GenerationModuleStepType,
)

KEY_PATTERN = r"^[a-z0-9][a-z0-9._-]*$"


class GenerationModuleInputDefinition(BaseModel):
    key: str = Field(min_length=1, max_length=150, pattern=KEY_PATTERN)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    input_type: GenerationModuleInputType
    position: int = Field(default=0, ge=0)
    is_required: bool = True
    default_value: Any | None = None
    validation: dict[str, Any] = Field(default_factory=dict)


class GenerationModuleOutputDefinition(BaseModel):
    key: str = Field(min_length=1, max_length=150, pattern=KEY_PATTERN)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    output_type: GenerationModuleOutputType
    position: int = Field(default=0, ge=0)
    is_required: bool = True
    source_step_key: str | None = Field(default=None, max_length=150)
    source_path: str | None = Field(default=None, max_length=500)
    metadata: dict[str, Any] = Field(default_factory=dict)


class GenerationModuleStepDefinition(BaseModel):
    key: str = Field(min_length=1, max_length=150, pattern=KEY_PATTERN)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    step_type: GenerationModuleStepType
    position: int = Field(default=0, ge=0)
    is_enabled: bool = True
    configuration: dict[str, Any] = Field(default_factory=dict)
    input_mapping: dict[str, Any] = Field(default_factory=dict)
    output_mapping: dict[str, Any] = Field(default_factory=dict)


class GenerationModuleCreate(BaseModel):
    key: str = Field(min_length=2, max_length=150, pattern=KEY_PATTERN)
    name: str = Field(min_length=2, max_length=255)
    description: str | None = None
    version: int = Field(default=1, ge=1)
    category: str = Field(default="tryon", min_length=2, max_length=100)
    default_execution_engine: GenerationExecutionEngine = (
        GenerationExecutionEngine.SIMULATED
    )
    metadata: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True
    inputs: list[GenerationModuleInputDefinition] = Field(default_factory=list)
    outputs: list[GenerationModuleOutputDefinition] = Field(default_factory=list)
    steps: list[GenerationModuleStepDefinition] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_keys_and_positions(self):
        for label, items in (
            ("input", self.inputs),
            ("output", self.outputs),
            ("step", self.steps),
        ):
            keys = [item.key for item in items]
            if len(keys) != len(set(keys)):
                raise ValueError(f"Duplicate {label} keys are not allowed.")

        positions = [item.position for item in self.steps]
        if len(positions) != len(set(positions)):
            raise ValueError("Duplicate step positions are not allowed.")

        step_keys = set(item.key for item in self.steps)
        invalid_sources = [
            item.source_step_key
            for item in self.outputs
            if item.source_step_key and item.source_step_key not in step_keys
        ]
        if invalid_sources:
            raise ValueError("Every output source_step_key must reference a module step.")
        return self


class GenerationModuleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = None
    category: str | None = Field(default=None, min_length=2, max_length=100)
    default_execution_engine: GenerationExecutionEngine | None = None
    metadata: dict[str, Any] | None = None
    is_active: bool | None = None
    inputs: list[GenerationModuleInputDefinition] | None = None
    outputs: list[GenerationModuleOutputDefinition] | None = None
    steps: list[GenerationModuleStepDefinition] | None = None

    @model_validator(mode="after")
    def validate_unique_keys_and_positions(self):
        for label, items in (
            ("input", self.inputs),
            ("output", self.outputs),
            ("step", self.steps),
        ):
            if items is None:
                continue
            keys = [item.key for item in items]
            if len(keys) != len(set(keys)):
                raise ValueError(f"Duplicate {label} keys are not allowed.")

        if self.steps is not None:
            positions = [item.position for item in self.steps]
            if len(positions) != len(set(positions)):
                raise ValueError("Duplicate step positions are not allowed.")
        return self


class GenerationModuleInputResponse(GenerationModuleInputDefinition):
    id: int
    created_at: datetime
    updated_at: datetime


class GenerationModuleOutputResponse(GenerationModuleOutputDefinition):
    id: int
    created_at: datetime
    updated_at: datetime


class GenerationModuleStepResponse(GenerationModuleStepDefinition):
    id: int
    created_at: datetime
    updated_at: datetime


class GenerationModuleResponse(BaseModel):
    id: int
    key: str
    name: str
    description: str | None
    version: int
    category: str
    default_execution_engine: GenerationExecutionEngine
    metadata: dict[str, Any]
    is_active: bool
    created_by_user_id: int | None
    inputs: list[GenerationModuleInputResponse]
    outputs: list[GenerationModuleOutputResponse]
    steps: list[GenerationModuleStepResponse]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class GenerationModuleListResponse(BaseModel):
    items: list[GenerationModuleResponse]
    total: int
    skip: int
    limit: int
