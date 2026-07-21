from pydantic import BaseModel, Field


class SimulatedEngineSettingsResponse(BaseModel):
    enabled: bool
    execution_mode: str
    delay_seconds: float
    failure_rate_percent: float
    copy_person_image_as_result: bool


class SimulatedEngineSettingsUpdate(BaseModel):
    enabled: bool
    execution_mode: str = Field(pattern=r"^(simulated|comfyui_local|runpod_serverless|auto)$")
    delay_seconds: float = Field(ge=0, le=30)
    failure_rate_percent: float = Field(ge=0, le=100)
    copy_person_image_as_result: bool = True


class SimulatedEngineTestResponse(BaseModel):
    available: bool
    provider: str
    status: str
    delay_seconds: float
    failure_rate_percent: float


class CommercialRepriceResponse(BaseModel):
    plans_updated: int
    packages_updated: int
    currency: str
    token_value_usd: float
    message: str
