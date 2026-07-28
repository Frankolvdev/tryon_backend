from pydantic import BaseModel, Field, model_validator


class ModalProviderConfig(BaseModel):
    enabled: bool = False
    token_id: str = Field(default="", max_length=500)
    token_secret: str = Field(default="", max_length=1000)
    environment: str = Field(default="main", min_length=1, max_length=120)
    app_name: str = Field(default="tryon-generation-runtime", min_length=1, max_length=120)
    runtime_url: str = Field(default="", max_length=1000)
    volume_name: str = Field(default="tryon-models", min_length=1, max_length=120)
    gpu: str = Field(default="L40S", min_length=1, max_length=120)
    timeout_seconds: int = Field(default=900, ge=60, le=86400)


class ModalProviderResponse(ModalProviderConfig):
    token_secret: str = ""
    token_secret_configured: bool = False


class ProviderActionResponse(BaseModel):
    success: bool
    message: str
    details: dict = {}


class RunPodProviderConfig(BaseModel):
    enabled: bool = False
    api_key: str = Field(default="", max_length=1000)
    s3_access_key: str = Field(default="", max_length=1000, description="Access Key de la S3 API de RunPod; es distinta de la API key normal.")
    s3_secret_key: str = Field(default="", max_length=1000, description="Secret de la S3 API de RunPod; se muestra una sola vez al crearlo.")
    endpoint_id: str = Field(default="", max_length=500, description="Opcional. Déjalo vacío para buscar o crear automáticamente el Endpoint durante el despliegue.")
    endpoint_name: str = Field(default="tryon-generation-runtime", min_length=1, max_length=191)
    template_id: str = Field(default="", max_length=500, description="Opcional. Déjalo vacío para buscar o crear automáticamente el Template durante el despliegue.")
    template_name: str = Field(default="tryon-generation-runtime", min_length=1, max_length=191)
    registry_auth_id: str = Field(default="", max_length=500, description="Solo es necesario cuando la imagen utiliza un registro Docker privado.")
    ghcr_username: str = Field(default="", max_length=191, description="Usuario u organización propietaria de la imagen en GitHub Container Registry.")
    ghcr_token: str = Field(default="", max_length=1000, description="Personal Access Token de GitHub con permisos read:packages y write:packages.")
    network_volume_id: str = Field(default="", max_length=500)
    network_volume_name: str = Field(default="tryon-models", min_length=1, max_length=120)
    network_volume_size_gb: int = Field(default=100, ge=1, le=4000)
    data_center_id: str = Field(default="", max_length=120)
    gpu_type_ids: list[str] = Field(default_factory=lambda: ["NVIDIA L40S"])
    allowed_cuda_versions: list[str] = Field(default_factory=lambda: ["12.8"])
    workers_min: int = Field(default=0, ge=0, le=128)
    workers_max: int = Field(default=5, ge=1, le=256)
    idle_timeout_seconds: int = Field(default=5, ge=1, le=3600)
    execution_timeout_seconds: int = Field(default=900, ge=60, le=86400)
    scaler_type: str = Field(default="QUEUE_DELAY", pattern="^(QUEUE_DELAY|REQUEST_COUNT)$")
    scaler_value: int = Field(default=4, ge=1, le=3600)
    flashboot: bool = True
    container_disk_gb: int = Field(default=100, ge=20, le=2000)
    timeout_seconds: int = Field(default=900, ge=60, le=86400)


class RunPodProviderResponse(RunPodProviderConfig):
    api_key: str = ""
    s3_secret_key: str = ""
    ghcr_token: str = ""
    api_key_configured: bool = False
    s3_secret_key_configured: bool = False
    ghcr_token_configured: bool = False


class BeamProviderConfig(BaseModel):
    enabled: bool = False
    api_key: str = Field(default="", max_length=1000)
    workspace: str = Field(default="", max_length=200)
    endpoint: str = Field(default="", max_length=1000)
    deployment_name: str = Field(default="tryon-generation-runtime", min_length=1, max_length=120)
    volume_name: str = Field(default="tryon-models", min_length=1, max_length=120)
    volume_mount_path: str = Field(default="/models", min_length=1, max_length=300)
    gpu: str = Field(default="H100", min_length=1, max_length=120)
    cpu: float = Field(default=8.0, ge=0.1, le=128)
    memory_mb: int = Field(default=65536, ge=128, le=1048576)
    workers: int = Field(default=1, ge=1, le=32)
    min_containers: int = Field(default=0, ge=0, le=128)
    max_containers: int = Field(default=5, ge=1, le=256)
    tasks_per_container: int = Field(default=1, ge=1, le=64)
    keep_warm_seconds: int = Field(default=10, ge=0, le=86400)
    max_pending_tasks: int = Field(default=100, ge=1, le=100000)
    retries: int = Field(default=2, ge=0, le=20)
    callback_url: str = Field(default="", max_length=1000)
    authorized: bool = True
    checkpoint_enabled: bool = False
    timeout_seconds: int = Field(default=900, ge=60, le=86400)

    @model_validator(mode="after")
    def validate_container_range(self):
        if self.max_containers < self.min_containers:
            raise ValueError("max_containers must be greater than or equal to min_containers")
        return self


class BeamProviderResponse(BeamProviderConfig):
    api_key: str = ""
    api_key_configured: bool = False
