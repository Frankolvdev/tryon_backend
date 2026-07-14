from pydantic import BaseModel


class AdminDashboardResponse(BaseModel):
    total_users: int
    active_users: int
    suspended_users: int
    deleted_users: int

    total_tryon_jobs: int
    completed_tryon_jobs: int
    failed_tryon_jobs: int
    queued_tryon_jobs: int

    total_tokens_issued: int
    total_tokens_consumed: int

    estimated_gpu_cost_cents: int
    actual_gpu_cost_cents: int
    total_storage_files: int