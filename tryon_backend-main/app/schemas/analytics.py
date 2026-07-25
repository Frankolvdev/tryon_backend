from datetime import date

from pydantic import BaseModel


class DailyMetricPoint(BaseModel):
    date: date
    value: int


class DailyCostPoint(BaseModel):
    date: date
    estimated_gpu_cost_cents: int
    actual_gpu_cost_cents: int


class AnalyticsSummaryResponse(BaseModel):
    total_users: int
    active_users: int
    total_tryon_jobs: int
    completed_tryon_jobs: int
    failed_tryon_jobs: int
    total_tokens_issued: int
    total_tokens_consumed: int
    estimated_gpu_cost_cents: int
    actual_gpu_cost_cents: int
    total_storage_files: int


class AnalyticsResponse(BaseModel):
    summary: AnalyticsSummaryResponse
    users_by_day: list[DailyMetricPoint]
    tryon_jobs_by_day: list[DailyMetricPoint]
    tokens_issued_by_day: list[DailyMetricPoint]
    tokens_consumed_by_day: list[DailyMetricPoint]
    gpu_costs_by_day: list[DailyCostPoint]