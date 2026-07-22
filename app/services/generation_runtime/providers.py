from __future__ import annotations

from dataclasses import dataclass

from app.common.generation_module_enums import GenerationExecutionEngine


@dataclass(frozen=True)
class RuntimeProviderDescriptor:
    key: str
    engine: GenerationExecutionEngine
    remote: bool
    supports_single_job_module_runtime: bool


class RuntimeProviderRegistry:
    _providers = {
        GenerationExecutionEngine.LOCAL_DOCKER: RuntimeProviderDescriptor(
            key="local", engine=GenerationExecutionEngine.LOCAL_DOCKER, remote=False,
            supports_single_job_module_runtime=True,
        ),
        GenerationExecutionEngine.RUNPOD_SERVERLESS: RuntimeProviderDescriptor(
            key="runpod_serverless", engine=GenerationExecutionEngine.RUNPOD_SERVERLESS, remote=True,
            supports_single_job_module_runtime=True,
        ),
        GenerationExecutionEngine.SIMULATED: RuntimeProviderDescriptor(
            key="simulated", engine=GenerationExecutionEngine.SIMULATED, remote=False,
            supports_single_job_module_runtime=True,
        ),
    }

    @classmethod
    def get(cls, engine: GenerationExecutionEngine) -> RuntimeProviderDescriptor:
        return cls._providers[engine]
