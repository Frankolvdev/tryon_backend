from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class RuntimeCustomNode(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    runtime_name: str = Field(default="generation-runtime", min_length=1, max_length=120, pattern=r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
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
    model_type: Literal["checkpoint", "vae", "lora", "controlnet", "clip", "upscaler", "diffusion_model", "embedding", "detector", "sam", "ipadapter", "video_model", "other"] = "other"
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
    project_key: str = Field(default="tryon", min_length=1, max_length=120)
    module_type: str = Field(default="tryon", min_length=1, max_length=120)
    container_workdir: str = Field(default="/app", min_length=1, max_length=1000)
    source_comfyui_path: str | None = Field(default=None, max_length=2000)
    workflow_filename: str | None = Field(default=None, max_length=500)
    workflow_json: dict | None = None
    last_index_summary: dict | None = None
    export_root_directory: str | None = Field(default=None, max_length=2000)
    export_directory: str | None = Field(default=None, max_length=2000)
    workspace_status: str = Field(default="draft", max_length=64)
    last_export_archive: str | None = Field(default=None, max_length=2000)
    last_export_manifest: dict | None = None
    last_exported_at: datetime | None = None
    is_active: bool = True


class RuntimeBuilderConfigResponse(RuntimeBuilderConfigUpdate):
    id: int
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)



class RuntimeWorkspaceUpdate(BaseModel):
    source_comfyui_path: str | None = Field(default=None, max_length=2000)
    workflow_filename: str | None = Field(default=None, max_length=500)
    workflow_json: dict | None = None
    container_workdir: str | None = Field(default=None, min_length=1, max_length=1000)
    export_root_directory: str | None = Field(default=None, max_length=2000)
    export_directory: str | None = Field(default=None, max_length=2000)
    project_key: str | None = Field(default=None, min_length=1, max_length=120)
    module_type: str | None = Field(default=None, min_length=1, max_length=120)

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


class RuntimeBuildCreate(BaseModel):
    push_after_build: bool = False

class RuntimeBuildResponse(BaseModel):
    id: int
    runtime_config_id: int
    version: str
    image_tag: str
    status: Literal["pending", "building", "validating", "succeeded", "failed", "publishing", "published", "active", "cancelled"]
    phase: str
    progress: int
    logs: str
    error_message: str | None
    image_id: str | None
    image_size_bytes: int | None
    manifest: dict
    validation_result: dict
    published: bool
    active: bool
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)

class RuntimeBuildListResponse(BaseModel):
    items: list[RuntimeBuildResponse]
    total: int

class RuntimeDockerDiagnosticResponse(BaseModel):
    docker_available: bool
    docker_version: str | None = None
    buildx_available: bool = False
    registry_image: str
    active_image: str | None = None
    message: str

class RuntimeImportPathRequest(BaseModel):
    path: str = Field(min_length=1, max_length=2000)
    include_all_models: bool = True

class RuntimeImportApplyRequest(BaseModel):
    report: dict
    selection: dict[str, bool] = Field(default_factory=lambda: {"base": True, "custom_nodes": True, "models": True, "dependencies": False, "volumes": True})

class RuntimeWorkflowAnalysisRequest(BaseModel):
    workflow: dict
    report: dict | None = None

class RuntimeWorkflowResolveRequest(BaseModel):
    path: str = Field(min_length=1, max_length=2000)
    workflow: dict
    workflow_filename: str | None = Field(default=None, max_length=500)


class RuntimeIntelligenceIndexRequest(BaseModel):
    path: str = Field(min_length=1, max_length=2000)

class RuntimeIntelligenceSearchRequest(BaseModel):
    path: str = Field(min_length=1, max_length=2000)
    query: str = Field(min_length=1, max_length=500)


class RuntimeContextGenerateRequest(BaseModel):
    comfyui_path: str = Field(min_length=1, max_length=2000)
    output_directory: str | None = Field(default=None, max_length=2000)
    copy_models: bool = True
    copy_custom_nodes: bool = True
    calculate_sha256: bool = True
    overwrite: bool = False

class RuntimeContextGenerateResponse(BaseModel):
    success: bool
    output_directory: str
    archive_path: str
    models_copied: int
    custom_nodes_copied: int
    bytes_copied: int
    files_generated: list[str]
    warnings: list[str]
    manifest: dict


class RuntimeModelVolumeAnalyzeRequest(BaseModel):
    comfyui_path: str = Field(min_length=1, max_length=2000)


class RuntimeModelVolumeExportRequest(BaseModel):
    comfyui_path: str = Field(min_length=1, max_length=2000)
    output_directory: str | None = Field(default=None, max_length=2000)
    destination_type: Literal["local", "docker_volume"] = "local"
    docker_volume: str | None = Field(default=None, max_length=255)
    docker_path: str = Field(default="models", max_length=2000)
    calculate_sha256: bool = True
    overwrite: bool = False
    skip_identical: bool = True


class RuntimeModelVolumeExportResponse(BaseModel):
    success: bool
    output_directory: str
    models_directory: str
    manifest_path: str
    destination_type: str = "local"
    docker_volume: str | None = None
    docker_path: str | None = None
    models_detected: int
    models_found: int
    models_missing: int
    models_copied: int
    models_skipped: int
    models_overwritten: int = 0
    errors: int = 0
    elapsed_seconds: float = 0
    destination: dict | None = None
    bytes_copied: int
    warnings: list[str]
    manifest: dict


class RuntimeContextJobCreateResponse(BaseModel):
    job_id: str
    status: str
    phase: str
    progress: int
    message: str
    error: str | None = None
    result: RuntimeContextGenerateResponse | RuntimeModelVolumeExportResponse | None = None
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None


class RuntimeContextJobResponse(RuntimeContextJobCreateResponse):
    pass


class RuntimeProjectResponse(RuntimeWorkspaceUpdate):
    id: int
    runtime_config_id: int | None = None
    project_key: str
    module_type: str
    container_workdir: str
    workspace_status: str
    last_index_summary: dict | None = None
    last_export_archive: str | None = None
    last_export_manifest: dict | None = None
    last_exported_at: datetime | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class RuntimeModelExportSettings(BaseModel):
    comfyui_path: str = ""
    output_directory: str = ""
    destination_type: Literal["local", "docker_volume"] = "local"
    docker_volume: str = ""
    docker_path: str = "models"
    calculate_sha256: bool = True
    overwrite: bool = False
    skip_identical: bool = True


class RuntimeLaunchSettings(BaseModel):
    build_name: str = "tryon-runtime"
    image_name: str = "tryon-runtime:latest"
    container_name: str = "tryon-comfyui"
    host_port: int = Field(default=8190, ge=1, le=65535)
    container_port: int = Field(default=8188, ge=1, le=65535)
    models_volume: str = ""
    workflows_volume: str = ""
    output_volume: str = ""
    models_mount_path: str = "/app/ComfyUI/models"
    workflows_mount_path: str = "/app/ComfyUI/user/default/workflows"
    output_mount_path: str = "/app/ComfyUI/output"
    gpu_mode: Literal["auto", "nvidia", "none"] = "nvidia"
    restart_policy: Literal["no", "always", "unless-stopped", "on-failure"] = "unless-stopped"
    extra_arguments: list[str] = Field(default_factory=list)


class RuntimeLaunchPreview(BaseModel):
    command: str
    lines: list[str]
