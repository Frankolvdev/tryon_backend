from pydantic import BaseModel, Field


class ModalProviderConfig(BaseModel):
    enabled: bool = False
    token_id: str = Field(default="", max_length=500)
    token_secret: str = Field(default="", max_length=1000)
    environment: str = Field(default="main", min_length=1, max_length=120)
    app_name: str = Field(default="tryon-generation-runtime", min_length=1, max_length=120)
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
