from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.repositories.base import BaseRepository


class AuditLogRepository(BaseRepository[AuditLog]):
    def __init__(self):
        super().__init__(AuditLog)

    def list_all(
        self,
        db: Session,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> list[AuditLog]:
        statement = (
            select(AuditLog)
            .order_by(AuditLog.created_at.desc())
            .offset(skip)
            .limit(limit)
        )

        return list(db.execute(statement).scalars().all())


audit_log_repository = AuditLogRepository()