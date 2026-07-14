from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.subscription_plan import SubscriptionPlan
from app.repositories.base import BaseRepository


class SubscriptionPlanRepository(BaseRepository[SubscriptionPlan]):
    def __init__(self):
        super().__init__(SubscriptionPlan)

    def get_by_key(
        self,
        db: Session,
        key: str,
    ) -> SubscriptionPlan | None:
        statement = select(SubscriptionPlan).where(
            SubscriptionPlan.key == key,
        )

        return db.execute(statement).scalar_one_or_none()

    def get_by_stripe_price_id(
        self,
        db: Session,
        stripe_price_id: str,
    ) -> SubscriptionPlan | None:
        statement = select(SubscriptionPlan).where(
            SubscriptionPlan.stripe_price_id == stripe_price_id,
        )

        return db.execute(statement).scalar_one_or_none()

    def list_all_filtered(
        self,
        db: Session,
        *,
        search: str | None = None,
        billing_interval: str | None = None,
        is_active: bool | None = None,
        is_public: bool | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[SubscriptionPlan]:
        statement = select(SubscriptionPlan)

        if search:
            pattern = f"%{search.strip()}%"

            statement = statement.where(
                or_(
                    SubscriptionPlan.key.ilike(pattern),
                    SubscriptionPlan.name.ilike(pattern),
                    SubscriptionPlan.description.ilike(pattern),
                )
            )

        if billing_interval is not None:
            statement = statement.where(
                SubscriptionPlan.billing_interval == billing_interval,
            )

        if is_active is not None:
            statement = statement.where(
                SubscriptionPlan.is_active.is_(is_active),
            )

        if is_public is not None:
            statement = statement.where(
                SubscriptionPlan.is_public.is_(is_public),
            )

        statement = (
            statement
            .order_by(
                SubscriptionPlan.sort_order.asc(),
                SubscriptionPlan.price_amount.asc(),
                SubscriptionPlan.id.asc(),
            )
            .offset(skip)
            .limit(limit)
        )

        return list(db.execute(statement).scalars().all())

    def count_filtered(
        self,
        db: Session,
        *,
        search: str | None = None,
        billing_interval: str | None = None,
        is_active: bool | None = None,
        is_public: bool | None = None,
    ) -> int:
        statement = select(func.count(SubscriptionPlan.id))

        if search:
            pattern = f"%{search.strip()}%"

            statement = statement.where(
                or_(
                    SubscriptionPlan.key.ilike(pattern),
                    SubscriptionPlan.name.ilike(pattern),
                    SubscriptionPlan.description.ilike(pattern),
                )
            )

        if billing_interval is not None:
            statement = statement.where(
                SubscriptionPlan.billing_interval == billing_interval,
            )

        if is_active is not None:
            statement = statement.where(
                SubscriptionPlan.is_active.is_(is_active),
            )

        if is_public is not None:
            statement = statement.where(
                SubscriptionPlan.is_public.is_(is_public),
            )

        return int(db.execute(statement).scalar_one())

    def list_public_active(
        self,
        db: Session,
        *,
        billing_interval: str | None = None,
    ) -> list[SubscriptionPlan]:
        statement = (
            select(SubscriptionPlan)
            .where(SubscriptionPlan.is_active.is_(True))
            .where(SubscriptionPlan.is_public.is_(True))
        )

        if billing_interval:
            statement = statement.where(
                SubscriptionPlan.billing_interval == billing_interval,
            )

        statement = statement.order_by(
            SubscriptionPlan.sort_order.asc(),
            SubscriptionPlan.price_amount.asc(),
            SubscriptionPlan.id.asc(),
        )

        return list(db.execute(statement).scalars().all())


subscription_plan_repository = SubscriptionPlanRepository()