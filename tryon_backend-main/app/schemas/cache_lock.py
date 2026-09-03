from pydantic import BaseModel, Field


class CacheLockAcquireRequest(BaseModel):
    name: str = Field(
        min_length=1,
        max_length=200,
    )

    ttl_seconds: int = Field(
        default=30,
        ge=1,
        le=3600,
    )

    wait_timeout_seconds: float = Field(
        default=0.0,
        ge=0.0,
        le=30.0,
    )


class CacheLockAcquireResponse(BaseModel):
    name: str
    owner: str
    acquired: bool
    ttl_seconds: int


class CacheLockReleaseRequest(BaseModel):
    name: str = Field(
        min_length=1,
        max_length=200,
    )

    owner: str = Field(
        min_length=10,
        max_length=500,
    )


class CacheLockReleaseResponse(BaseModel):
    name: str
    released: bool