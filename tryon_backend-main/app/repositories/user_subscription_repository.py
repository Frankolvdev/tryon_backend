from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.billing_enums import SubscriptionStatus
from app.models.user_subscription import UserSubscription
from app.repositories.base import BaseRepository


ACTIVE_SUBSCRIPTION_STATUSES = [
    SubscriptionStatus.INCOMPLETE.value,
    SubscriptionStatus.TRIALING.value,
    SubscriptionStatus.ACTIVE.value,
    SubscriptionStatus.PAST_DUE.value,
    SubscriptionStatus.UNPAID.value,
    SubscriptionStatus.PAUSED.value,
]


class UserSubscriptionRepository(BaseRepository[UserSubscription]):
    def __init__(self):
        super().__init__(UserSubscription)

    def get_by_provider_subscription_id(
        self,
        db: Session,
        *,
        provider_subscription_id: str,
    ) -> UserSubscription | None:
        statement = select(UserSubscription).where(
            UserSubscription.provider_subscription_id
            == provider_subscription_id
        )

        return db.execute(statement).scalar_one_or_none()

    def get_current_by_user_id(
        self,
        db: Session,
        *,
        user_id: int,
    ) -> UserSubscription | None:
        statement = (
            select(UserSubscription)
            .where(UserSubscription.user_id == user_id)
            .where(
                UserSubscription.status.in_(
                    ACTIVE_SUBSCRIPTION_STATUSES
                )
            )
            .order_by(UserSubscription.created_at.desc())
            .limit(1)
        )

        return db.execute(statement).scalar_one_or_none()

    def get_latest_by_user_id(
        self,
        db: Session,
        *,
        user_id: int,
    ) -> UserSubscription | None:
        statement = (
            select(UserSubscription)
            .where(UserSubscription.user_id == user_id)
            .order_by(UserSubscription.created_at.desc())
            .limit(1)
        )

        return db.execute(statement).scalar_one_or_none()

    def list_all_filtered(
        self,
        db: Session,
        *,
        user_id: int | None = None,
        status: str | None = None,
        plan_id: int | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[UserSubscription]:
        statement = select(UserSubscription)

        if user_id is not None:
            statement = statement.where(
                UserSubscription.user_id == user_id
            )

        if status is not None:
            statement = statement.where(
                UserSubscription.status == status
            )

        if plan_id is not None:
            statement = statement.where(
                UserSubscription.subscription_plan_id == plan_id
            )

        statement = (
            statement
            .order_by(UserSubscription.created_at.desc())
            .offset(skip)
            .limit(limit)
        )

        return list(db.execute(statement).scalars().all())

    def count_filtered(
        self,
        db: Session,
        *,
        user_id: int | None = None,
        status: str | None = None,
        plan_id: int | None = None,
    ) -> int:
        statement = select(func.count(UserSubscription.id))

        if user_id is not None:
            statement = statement.where(
                UserSubscription.user_id == user_id
            )

        if status is not None:
            statement = statement.where(
                UserSubscription.status == status
            )

        if plan_id is not None:
            statement = statement.where(
                UserSubscription.subscription_plan_id == plan_id
            )

        return int(db.execute(statement).scalar_one())


user_subscription_repository = UserSubscriptionRepository()