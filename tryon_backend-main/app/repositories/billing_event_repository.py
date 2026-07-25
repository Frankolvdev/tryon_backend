from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.billing_event import BillingEvent
from app.repositories.base import BaseRepository


class BillingEventRepository(BaseRepository[BillingEvent]):
    def __init__(self):
        super().__init__(BillingEvent)

    def get_by_provider_event_id(
        self,
        db: Session,
        *,
        provider: str,
        provider_event_id: str,
    ) -> BillingEvent | None:
        statement = (
            select(BillingEvent)
            .where(BillingEvent.provider == provider)
            .where(
                BillingEvent.provider_event_id
                == provider_event_id
            )
        )

        return db.execute(statement).scalar_one_or_none()

    def get_for_update(
        self,
        db: Session,
        *,
        event_id: int,
    ) -> BillingEvent | None:
        statement = (
            select(BillingEvent)
            .where(BillingEvent.id == event_id)
            .with_for_update()
        )

        return db.execute(statement).scalar_one_or_none()

    def create_if_missing(
        self,
        db: Session,
        *,
        data: dict,
    ) -> tuple[BillingEvent, bool]:
        existing = self.get_by_provider_event_id(
            db,
            provider=data["provider"],
            provider_event_id=data["provider_event_id"],
        )

        if existing:
            return existing, False

        event = BillingEvent(**data)

        try:
            db.add(event)
            db.commit()
            db.refresh(event)

            return event, True

        except IntegrityError:
            db.rollback()

            existing = self.get_by_provider_event_id(
                db,
                provider=data["provider"],
                provider_event_id=data["provider_event_id"],
            )

            if not existing:
                raise

            return existing, False

    def list_all_filtered(
        self,
        db: Session,
        *,
        event_type: str | None = None,
        status: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[BillingEvent]:
        statement = select(BillingEvent)

        if event_type:
            statement = statement.where(
                BillingEvent.event_type == event_type
            )

        if status:
            statement = statement.where(
                BillingEvent.status == status
            )

        statement = (
            statement
            .order_by(BillingEvent.received_at.desc())
            .offset(skip)
            .limit(limit)
        )

        return list(db.execute(statement).scalars().all())

    def count_filtered(
        self,
        db: Session,
        *,
        event_type: str | None = None,
        status: str | None = None,
    ) -> int:
        statement = select(func.count(BillingEvent.id))

        if event_type:
            statement = statement.where(
                BillingEvent.event_type == event_type
            )

        if status:
            statement = statement.where(
                BillingEvent.status == status
            )

        return int(db.execute(statement).scalar_one())


billing_event_repository = BillingEventRepository()