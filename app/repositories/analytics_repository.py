from datetime import date, datetime, timedelta

from sqlalchemy import Date, cast, func, select
from sqlalchemy.orm import Session

from app.common.enums import TokenTransactionType, TryOnJobStatus
from app.models.storage_file import StorageFile
from app.models.token_transaction import TokenTransaction
from app.models.tryon_job import TryOnJob
from app.models.user import User


class AnalyticsRepository:
    def _date_range(self, days: int) -> list[date]:
        today = datetime.utcnow().date()
        start = today - timedelta(days=days - 1)
        return [start + timedelta(days=index) for index in range(days)]

    def count_users(self, db: Session) -> int:
        return int(db.execute(select(func.count()).select_from(User)).scalar_one())

    def count_active_users(self, db: Session) -> int:
        statement = (
            select(func.count())
            .select_from(User)
            .where(User.is_active.is_(True))
            .where(User.deleted_at.is_(None))
        )
        return int(db.execute(statement).scalar_one())

    def count_tryon_jobs(self, db: Session) -> int:
        return int(db.execute(select(func.count()).select_from(TryOnJob)).scalar_one())

    def count_tryon_jobs_by_status(
        self,
        db: Session,
        status: TryOnJobStatus,
    ) -> int:
        statement = (
            select(func.count())
            .select_from(TryOnJob)
            .where(TryOnJob.status == status.value)
        )
        return int(db.execute(statement).scalar_one())

    def sum_tokens_issued(self, db: Session) -> int:
        statement = (
            select(func.coalesce(func.sum(TokenTransaction.amount), 0))
            .where(TokenTransaction.transaction_type == TokenTransactionType.CREDIT.value)
        )
        return int(db.execute(statement).scalar_one())

    def sum_tokens_consumed(self, db: Session) -> int:
        statement = (
            select(func.coalesce(func.sum(TokenTransaction.amount), 0))
            .where(TokenTransaction.transaction_type == TokenTransactionType.DEBIT.value)
        )
        return abs(int(db.execute(statement).scalar_one()))

    def sum_estimated_gpu_cost_cents(self, db: Session) -> int:
        statement = select(func.coalesce(func.sum(TryOnJob.estimated_gpu_cost_cents), 0))
        return int(db.execute(statement).scalar_one())

    def sum_actual_gpu_cost_cents(self, db: Session) -> int:
        statement = select(func.coalesce(func.sum(TryOnJob.actual_gpu_cost_cents), 0))
        return int(db.execute(statement).scalar_one())

    def count_storage_files(self, db: Session) -> int:
        return int(db.execute(select(func.count()).select_from(StorageFile)).scalar_one())

    def users_by_day(self, db: Session, days: int) -> dict[date, int]:
        start_date = self._date_range(days)[0]

        statement = (
            select(
                cast(User.created_at, Date).label("day"),
                func.count(User.id),
            )
            .where(User.created_at >= start_date)
            .group_by("day")
            .order_by("day")
        )

        return {row[0]: int(row[1]) for row in db.execute(statement).all()}

    def tryon_jobs_by_day(self, db: Session, days: int) -> dict[date, int]:
        start_date = self._date_range(days)[0]

        statement = (
            select(
                cast(TryOnJob.created_at, Date).label("day"),
                func.count(TryOnJob.id),
            )
            .where(TryOnJob.created_at >= start_date)
            .group_by("day")
            .order_by("day")
        )

        return {row[0]: int(row[1]) for row in db.execute(statement).all()}

    def tokens_by_day(
        self,
        db: Session,
        days: int,
        transaction_type: TokenTransactionType,
    ) -> dict[date, int]:
        start_date = self._date_range(days)[0]

        statement = (
            select(
                cast(TokenTransaction.created_at, Date).label("day"),
                func.coalesce(func.sum(TokenTransaction.amount), 0),
            )
            .where(TokenTransaction.created_at >= start_date)
            .where(TokenTransaction.transaction_type == transaction_type.value)
            .group_by("day")
            .order_by("day")
        )

        values = {}

        for row in db.execute(statement).all():
            value = int(row[1])
            if transaction_type == TokenTransactionType.DEBIT:
                value = abs(value)

            values[row[0]] = value

        return values

    def gpu_costs_by_day(self, db: Session, days: int) -> dict[date, dict[str, int]]:
        start_date = self._date_range(days)[0]

        statement = (
            select(
                cast(TryOnJob.created_at, Date).label("day"),
                func.coalesce(func.sum(TryOnJob.estimated_gpu_cost_cents), 0),
                func.coalesce(func.sum(TryOnJob.actual_gpu_cost_cents), 0),
            )
            .where(TryOnJob.created_at >= start_date)
            .group_by("day")
            .order_by("day")
        )

        return {
            row[0]: {
                "estimated_gpu_cost_cents": int(row[1]),
                "actual_gpu_cost_cents": int(row[2]),
            }
            for row in db.execute(statement).all()
        }


analytics_repository = AnalyticsRepository()