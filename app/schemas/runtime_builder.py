from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class RuntimeCustomNode(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    repository: str = Field(min_length=1, max_length=1000)
    commit: str | None = Field(default=None, max_length=128)
    enabled: bool = True
    install_requirements: bool = True


class RuntimePythonDependency(BaseModel):
    package: str = Field(min_length=1, max_length=255)
    version: str | None = Field(default=None, max_length=128)
    enabled: bool = True


class RuntimeModelAsset(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    model_type: Literal["checkpoint", "vae", "lora", "controlnet", "clip", "upscaler", "other"] = "other"
    source_url: str | None = Field(default=None, max_length=2000)
    target_path: str = Field(min_length=1, max_length=1000)
    sha256: str | None = Field(default=None, max_length=64)
    strategy: Literal["image", "volume", "startup-download"] = "volume"
    enabled: bool = True


class RuntimeEnvironmentVariable(BaseModel):
    key: str = Field(pattern=r"^[A-Z_][A-Z0-9_]*$", max_length=255)
    value: str | None = None
    secret: bool = False
    required: bool = False


class RuntimeVolume(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    mount_path: str = Field(min_length=1, max_length=1000)
    read_only: bool = False


class RuntimeBuilderConfigUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    runtime_version: str = Field(min_length=1, max_length=64)
    python_version: str = Field(min_length=1, max_length=32)
    cuda_version: str = Field(min_length=1, max_length=32)
    pytorch_index_url: str = Field(min_length=1, max_length=1000)
    comfyui_repository: str = Field(min_length=1, max_length=1000)
    comfyui_commit: str | None = Field(default=None, max_length=128)
    target_platform: str = Field(min_length=1, max_length=64)
    registry_image: str = Field(min_length=1, max_length=500)
    include_comfyui_manager: bool = False
    custom_nodes: list[RuntimeCustomNode] = Field(default_factory=list)
    python_dependencies: list[RuntimePythonDependency] = Field(default_factory=list)
    models: list[RuntimeModelAsset] = Field(default_factory=list)
    environment_variables: list[RuntimeEnvironmentVariable] = Field(default_factory=list)
    volumes: list[RuntimeVolume] = Field(default_factory=list)
    notes: str | None = None
    is_active: bool = True


class RuntimeBuilderConfigResponse(RuntimeBuilderConfigUpdate):
    id: int
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class RuntimeValidationIssue(BaseModel):
    level: Literal["error", "warning", "info"]
    field: str
    message: str


class RuntimeValidationResponse(BaseModel):
    valid: bool
    issues: list[RuntimeValidationIssue]
    summary: dict[str, int | str | bool]


class RuntimeGeneratedFilesResponse(BaseModel):
    dockerfile: str
    entrypoint: str
    runtime_manifest: dict
    custom_nodes_lock: dict
    models_manifest: dict
    env_example: str
