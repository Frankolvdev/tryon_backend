from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.generation_module import KEY_PATTERN



PORT_TYPE_PATTERN = r"^(image|images|mask|file|text|integer|float|boolean|json|metadata|auto)$"


class GenerationNodePort(BaseModel):
    id: str = Field(min_length=1, max_length=150, pattern=KEY_PATTERN)
    label: str = Field(min_length=1, max_length=255)
    data_type: str = Field(default="auto", pattern=PORT_TYPE_PATTERN)
    node_id: str | None = Field(default=None, max_length=100)
    field: str | None = Field(default=None, max_length=150)
    is_required: bool = True

class WorkflowInputBinding(BaseModel):
    module_input_key: str | None = Field(default=None, min_length=1, max_length=150, pattern=KEY_PATTERN)
    source_path: str | None = Field(default=None, min_length=1, max_length=300)
    node_id: str = Field(min_length=1, max_length=100)
    input_field: str = Field(min_length=1, max_length=150)

    @model_validator(mode="after")
    def require_source(self):
        if not self.module_input_key and not self.source_path:
            raise ValueError("Either module_input_key or source_path is required.")
        return self


class WorkflowOutputBinding(BaseModel):
    module_output_key: str = Field(min_length=1, max_length=150, pattern=KEY_PATTERN)
    node_id: str = Field(min_length=1, max_length=100)


class WorkflowStepImportRequest(BaseModel):
    key: str = Field(min_length=1, max_length=150, pattern=KEY_PATTERN)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    position: int = Field(ge=0)
    workflow_name: str | None = Field(default=None, max_length=255)
    workflow_json: dict[str, Any]
    input_bindings: list[WorkflowInputBinding] = Field(default_factory=list)
    output_bindings: list[WorkflowOutputBinding] = Field(default_factory=list)
    input_ports: list[GenerationNodePort] = Field(default_factory=list)
    output_ports: list[GenerationNodePort] = Field(default_factory=list)
    is_enabled: bool = True

    @field_validator("workflow_json")
    @classmethod
    def workflow_must_not_be_empty(cls, value: dict[str, Any]):
        if not value:
            raise ValueError("The ComfyUI workflow cannot be empty.")
        return value

    @model_validator(mode="after")
    def binding_keys_must_be_unique(self):
        input_targets = [(item.node_id, item.input_field) for item in self.input_bindings]
        if len(input_targets) != len(set(input_targets)):
            raise ValueError("A workflow input target can only be bound once.")
        output_keys = [item.module_output_key for item in self.output_bindings]
        if len(output_keys) != len(set(output_keys)):
            raise ValueError("A module output can only be bound once in a workflow step.")
        return self


class WorkflowStepBindingsUpdate(BaseModel):
    input_bindings: list[WorkflowInputBinding] = Field(default_factory=list)
    output_bindings: list[WorkflowOutputBinding] = Field(default_factory=list)


class WorkflowStepUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    workflow_name: str | None = Field(default=None, max_length=255)
    workflow_json: dict[str, Any] | None = None
    input_bindings: list[WorkflowInputBinding] | None = None
    output_bindings: list[WorkflowOutputBinding] | None = None
    input_ports: list[GenerationNodePort] | None = None
    output_ports: list[GenerationNodePort] | None = None
    is_enabled: bool | None = None

    @field_validator("workflow_json")
    @classmethod
    def workflow_must_not_be_empty(cls, value: dict[str, Any] | None):
        if value is not None and not value:
            raise ValueError("The ComfyUI workflow cannot be empty.")
        return value


class PythonStepCreateRequest(BaseModel):
    key: str = Field(min_length=1, max_length=150, pattern=KEY_PATTERN)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    position: int = Field(ge=0)
    source_code: str = Field(min_length=1)
    entrypoint: str = Field(default="run", min_length=1, max_length=100)
    timeout_seconds: int = Field(default=300, ge=1, le=3600)
    input_mapping: dict[str, Any] = Field(default_factory=dict)
    output_mapping: dict[str, Any] = Field(default_factory=dict)
    input_ports: list[GenerationNodePort] = Field(default_factory=list)
    output_ports: list[GenerationNodePort] = Field(default_factory=list)
    is_enabled: bool = True


class PythonStepUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    source_code: str | None = Field(default=None, min_length=1)
    entrypoint: str | None = Field(default=None, min_length=1, max_length=100)
    timeout_seconds: int | None = Field(default=None, ge=1, le=3600)
    input_mapping: dict[str, Any] | None = None
    output_mapping: dict[str, Any] | None = None
    input_ports: list[GenerationNodePort] | None = None
    output_ports: list[GenerationNodePort] | None = None
    is_enabled: bool | None = None


class PythonSourceAnalysisRequest(BaseModel):
    source_code: str = Field(min_length=1)
    entrypoint: str = Field(default="run", min_length=1, max_length=100)


class PythonSourceAnalysisResponse(BaseModel):
    valid: bool
    entrypoint_found: bool
    input_keys: list[str] = Field(default_factory=list)
    output_keys: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class StepReorderItem(BaseModel):
    step_id: int = Field(gt=0)
    position: int = Field(ge=0)


class GenerationModuleStepsReorderRequest(BaseModel):
    items: list[StepReorderItem] = Field(min_length=1)

    @model_validator(mode="after")
    def ids_and_positions_must_be_unique(self):
        ids = [item.step_id for item in self.items]
        positions = [item.position for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate step ids are not allowed.")
        if len(positions) != len(set(positions)):
            raise ValueError("Duplicate step positions are not allowed.")
        return self


class WorkflowValidationResponse(BaseModel):
    valid: bool
    node_count: int
    node_ids: list[str]
    class_types: list[str]
