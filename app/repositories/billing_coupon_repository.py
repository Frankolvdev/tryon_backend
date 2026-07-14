from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.billing_coupon import BillingCoupon
from app.repositories.base import BaseRepository


class BillingCouponRepository(BaseRepository[BillingCoupon]):
    def __init__(self):
        super().__init__(BillingCoupon)

    def get_by_code(
        self,
        db: Session,
        code: str,
    ) -> BillingCoupon | None:
        statement = select(BillingCoupon).where(
            BillingCoupon.code == code.upper(),
        )

        return db.execute(statement).scalar_one_or_none()

    def list_filtered(
        self,
        db: Session,
        *,
        search: str | None = None,
        is_active: bool | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[BillingCoupon]:
        statement = select(BillingCoupon)

        if search:
            pattern = f"%{search.strip()}%"

            statement = statement.where(
                or_(
                    BillingCoupon.code.ilike(pattern),
                    BillingCoupon.name.ilike(pattern),
                    BillingCoupon.description.ilike(pattern),
                )
            )

        if is_active is not None:
            statement = statement.where(
                BillingCoupon.is_active.is_(is_active),
            )

        statement = (
            statement
            .order_by(BillingCoupon.created_at.desc())
            .offset(skip)
            .limit(limit)
        )

        return list(db.execute(statement).scalars().all())

    def count_filtered(
        self,
        db: Session,
        *,
        search: str | None = None,
        is_active: bool | None = None,
    ) -> int:
        statement = select(func.count(BillingCoupon.id))

        if search:
            pattern = f"%{search.strip()}%"

            statement = statement.where(
                or_(
                    BillingCoupon.code.ilike(pattern),
                    BillingCoupon.name.ilike(pattern),
                    BillingCoupon.description.ilike(pattern),
                )
            )

        if is_active is not None:
            statement = statement.where(
                BillingCoupon.is_active.is_(is_active),
            )

        return int(db.execute(statement).scalar_one())


billing_coupon_repository = BillingCouponRepository()