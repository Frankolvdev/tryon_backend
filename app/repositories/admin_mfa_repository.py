from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.admin_mfa_credential import (
    AdminMfaCredential,
)


class AdminMfaRepository:
    def get_by_user_id(
        self,
        db: Session,
        *,
        user_id: int,
    ) -> AdminMfaCredential | None:
        statement = select(
            AdminMfaCredential
        ).where(
            AdminMfaCredential.user_id
            == user_id
        )

        return db.execute(
            statement
        ).scalar_one_or_none()


admin_mfa_repository = (
    AdminMfaRepository()
)