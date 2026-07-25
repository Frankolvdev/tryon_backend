from typing import Literal

from pydantic import BaseModel, Field, model_validator


ModalGpu = Literal["L4", "L40S", "A10G", "A100-40GB", "A100-80GB", "H100"]


class AiEngineSettingsUpdate(BaseModel):
    local_parallel_executions: int = Field(ge=1, le=32)

    # Se conservan para compatibilidad con el despachador RunPod existente,
    # aunque ya no se editan desde la vista Motor IA.
    runpod_min_workers: int = Field(ge=0, le=128)
    runpod_max_workers: int = Field(ge=1, le=256)
    runpod_dispatch_workers: int = Field(ge=1, le=128)
    runpod_max_in_flight: int = Field(ge=1, le=512)

    modal_gpu: ModalGpu = "L40S"
    modal_min_containers: int = Field(default=0, ge=0, le=100)
    modal_max_containers: int = Field(default=3, ge=1, le=100)
    modal_concurrency: int = Field(default=1, ge=1, le=16)
    modal_input_concurrency: int = Field(default=1000, ge=1, le=1000)
    modal_scaledown_window_seconds: int = Field(default=300, ge=60, le=3600)
    modal_execution_timeout_seconds: int = Field(default=1800, ge=60, le=86400)

    queue_block_seconds: int = Field(ge=1, le=60)

    @model_validator(mode="after")
    def validate_ranges(self):
        if self.runpod_max_workers < self.runpod_min_workers:
            raise ValueError("runpod_max_workers must be greater than or equal to runpod_min_workers")
        if self.modal_max_containers < self.modal_min_containers:
            raise ValueError("modal_max_containers must be greater than or equal to modal_min_containers")
        return self


class AiEngineSettingsResponse(AiEngineSettingsUpdate):
    effective_runpod_parallelism: int
    requires_restart: bool = True
