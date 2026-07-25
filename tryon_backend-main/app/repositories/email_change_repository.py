from datetime import datetime

from sqlalchemy import (
    func,
    select,
    update,
)
from sqlalchemy.orm import Session

from app.models.email_change_request import (
    EmailChangeRequest,
)


class EmailChangeRepository:
    def get_by_id(
        self,
        db: Session,
        *,
        request_id: int,
    ) -> EmailChangeRequest | None:
        return db.get(
            EmailChangeRequest,
            request_id,
        )

    def get_pending_for_user(
        self,
        db: Session,
        *,
        user_id: int,
    ) -> EmailChangeRequest | None:
        statement = (
            select(EmailChangeRequest)
            .where(
                EmailChangeRequest.user_id
                == user_id,
                EmailChangeRequest.status
                == "pending",
            )
            .order_by(
                EmailChangeRequest
                .created_at
                .desc()
            )
            .limit(1)
        )

        return db.execute(
            statement
        ).scalar_one_or_none()

    def get_pending_for_confirmation(
        self,
        db: Session,
        *,
        user_id: int,
        new_email: str,
    ) -> EmailChangeRequest | None:
        statement = (
            select(EmailChangeRequest)
            .where(
                EmailChangeRequest.user_id
                == user_id,
                func.lower(
                    EmailChangeRequest.new_email
                )
                == new_email.lower(),
                EmailChangeRequest.status
                == "pending",
            )
            .order_by(
                EmailChangeRequest
                .created_at
                .desc()
            )
            .limit(1)
        )

        return db.execute(
            statement
        ).scalar_one_or_none()

    def count_since(
        self,
        db: Session,
        *,
        user_id: int,
        created_from: datetime,
    ) -> int:
        statement = select(
            func.count(
                EmailChangeRequest.id
            )
        ).where(
            EmailChangeRequest.user_id
            == user_id,
            EmailChangeRequest.created_at
            >= created_from,
        )

        return int(
            db.execute(
                statement
            ).scalar_one()
        )

    def cancel_pending(
        self,
        db: Session,
        *,
        user_id: int,
    ) -> int:
        result = db.execute(
            update(EmailChangeRequest)
            .where(
                EmailChangeRequest.user_id
                == user_id,
                EmailChangeRequest.status
                == "pending",
            )
            .values(
                status="cancelled",
            )
        )

        return int(
            result.rowcount or 0
        )

    def list_requests(
        self,
        db: Session,
        *,
        user_id: int | None = None,
        status: str | None = None,
        search: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[EmailChangeRequest]:
        statement = select(
            EmailChangeRequest
        )

        if user_id is not None:
            statement = statement.where(
                EmailChangeRequest.user_id
                == user_id
            )

        if status:
            statement = statement.where(
                EmailChangeRequest.status
                == status
            )

        if search:
            pattern = (
                f"%{search.strip()}%"
            )

            statement = statement.where(
                (
                    EmailChangeRequest
                    .current_email
                    .ilike(pattern)
                )
                |
                (
                    EmailChangeRequest
                    .new_email
                    .ilike(pattern)
                )
            )

        statement = (
            statement
            .order_by(
                EmailChangeRequest
                .created_at
                .desc()
            )
            .offset(skip)
            .limit(limit)
        )

        return list(
            db.execute(
                statement
            ).scalars().all()
        )

    def count_requests(
        self,
        db: Session,
        *,
        user_id: int | None = None,
        status: str | None = None,
        search: str | None = None,
    ) -> int:
        statement = select(
            func.count(
                EmailChangeRequest.id
            )
        )

        if user_id is not None:
            statement = statement.where(
                EmailChangeRequest.user_id
                == user_id
            )

        if status:
            statement = statement.where(
                EmailChangeRequest.status
                == status
            )

        if search:
            pattern = (
                f"%{search.strip()}%"
            )

            statement = statement.where(
                (
                    EmailChangeRequest
                    .current_email
                    .ilike(pattern)
                )
                |
                (
                    EmailChangeRequest
                    .new_email
                    .ilike(pattern)
                )
            )

        return int(
            db.execute(
                statement
            ).scalar_one()
        )


email_change_repository = (
    EmailChangeRepository()
)