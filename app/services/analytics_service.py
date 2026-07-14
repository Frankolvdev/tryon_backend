from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.common.enums import TokenTransactionType, TryOnJobStatus
from app.repositories.analytics_repository import analytics_repository
from app.schemas.analytics import (
    AnalyticsResponse,
    AnalyticsSummaryResponse,
    DailyCostPoint,
    DailyMetricPoint,
)


class AnalyticsService:
    def _date_range(self, days: int) -> list[date]:
        today = datetime.utcnow().date()
        start = today - timedelta(days=days - 1)
        return [start + timedelta(days=index) for index in range(days)]

    def get_analytics(
        self,
        db: Session,
        *,
        days: int = 30,
    ) -> AnalyticsResponse:
        date_range = self._date_range(days)

        users_by_day = analytics_repository.users_by_day(db, days)
        tryon_jobs_by_day = analytics_repository.tryon_jobs_by_day(db, days)
        tokens_issued_by_day = analytics_repository.tokens_by_day(
            db,
            days,
            TokenTransactionType.CREDIT,
        )
        tokens_consumed_by_day = analytics_repository.tokens_by_day(
            db,
            days,
            TokenTransactionType.DEBIT,
        )
        gpu_costs_by_day = analytics_repository.gpu_costs_by_day(db, days)

        return AnalyticsResponse(
            summary=AnalyticsSummaryResponse(
                total_users=analytics_repository.count_users(db),
                active_users=analytics_repository.count_active_users(db),
                total_tryon_jobs=analytics_repository.count_tryon_jobs(db),
                completed_tryon_jobs=analytics_repository.count_tryon_jobs_by_status(
                    db,
                    TryOnJobStatus.COMPLETED,
                ),
                failed_tryon_jobs=analytics_repository.count_tryon_jobs_by_status(
                    db,
                    TryOnJobStatus.FAILED,
                ),
                total_tokens_issued=analytics_repository.sum_tokens_issued(db),
                total_tokens_consumed=analytics_repository.sum_tokens_consumed(db),
                estimated_gpu_cost_cents=analytics_repository.sum_estimated_gpu_cost_cents(db),
                actual_gpu_cost_cents=analytics_repository.sum_actual_gpu_cost_cents(db),
                total_storage_files=analytics_repository.count_storage_files(db),
            ),
            users_by_day=[
                DailyMetricPoint(date=day, value=users_by_day.get(day, 0))
                for day in date_range
            ],
            tryon_jobs_by_day=[
                DailyMetricPoint(date=day, value=tryon_jobs_by_day.get(day, 0))
                for day in date_range
            ],
            tokens_issued_by_day=[
                DailyMetricPoint(date=day, value=tokens_issued_by_day.get(day, 0))
                for day in date_range
            ],
            tokens_consumed_by_day=[
                DailyMetricPoint(date=day, value=tokens_consumed_by_day.get(day, 0))
                for day in date_range
            ],
            gpu_costs_by_day=[
                DailyCostPoint(
                    date=day,
                    estimated_gpu_cost_cents=gpu_costs_by_day.get(
                        day,
                        {},
                    ).get("estimated_gpu_cost_cents", 0),
                    actual_gpu_cost_cents=gpu_costs_by_day.get(
                        day,
                        {},
                    ).get("actual_gpu_cost_cents", 0),
                )
                for day in date_range
            ],
        )


analytics_service = AnalyticsService()