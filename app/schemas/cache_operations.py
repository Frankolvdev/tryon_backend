from pydantic import BaseModel, Field


class CacheWarmupRequest(BaseModel):
    include_settings: bool = True
    include_feature_flags: bool = True
    include_pricing: bool = True
    include_subscription_plans: bool = True
    include_token_packages: bool = True
    include_workflows: bool = True


class CacheWarmupItemResult(BaseModel):
    name: str
    success: bool
    loaded_items: int
    message: str


class CacheWarmupResponse(BaseModel):
    success: bool
    items: list[CacheWarmupItemResult] = Field(
        default_factory=list
    )

    total_loaded_items: int
    failures: int