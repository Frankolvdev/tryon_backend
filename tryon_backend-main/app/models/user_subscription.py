from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.common.billing_enums import BillingProvider, SubscriptionStatus
from app.common.time import utc_now
from app.db.database import Base


class UserSubscription(Base):
    __tablename__ = "user_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    subscription_plan_id: Mapped[int] = mapped_column(
        ForeignKey("subscription_plans.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    billing_customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("billing_customers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    provider: Mapped[str] = mapped_column(
        String(50),
        default=BillingProvider.STRIPE.value,
        nullable=False,
        index=True,
    )

    provider_subscription_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        unique=True,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        default=SubscriptionStatus.INCOMPLETE.value,
        nullable=False,
        index=True,
    )

    current_period_start: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    current_period_end: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        index=True,
    )

    trial_start: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    trial_end: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    cancel_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    canceled_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    cancel_at_period_end: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    last_tokens_granted_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )