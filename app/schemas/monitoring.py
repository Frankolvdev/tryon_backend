from pydantic import BaseModel


class ServiceHealthResponse(BaseModel):
    service: str
    status: str
    details: dict | None = None


class SystemResourcesResponse(BaseModel):
    cpu_percent: float
    memory_percent: float
    disk_percent: float


class MonitoringResponse(BaseModel):
    api: ServiceHealthResponse
    database: ServiceHealthResponse
    redis: ServiceHealthResponse
    storage: ServiceHealthResponse
    resources: SystemResourcesResponse