from pydantic import BaseModel, Field, model_validator


class AiEngineSettingsUpdate(BaseModel):
    local_parallel_executions: int = Field(ge=1, le=32)
    runpod_min_workers: int = Field(ge=0, le=128)
    runpod_max_workers: int = Field(ge=1, le=256)
    runpod_dispatch_workers: int = Field(ge=1, le=128)
    runpod_max_in_flight: int = Field(ge=1, le=512)
    queue_block_seconds: int = Field(ge=1, le=60)

    @model_validator(mode="after")
    def validate_runpod_worker_range(self):
        if self.runpod_max_workers < self.runpod_min_workers:
            raise ValueError("runpod_max_workers must be greater than or equal to runpod_min_workers")
        return self


class AiEngineSettingsResponse(AiEngineSettingsUpdate):
    effective_runpod_parallelism: int
    requires_restart: bool = True
