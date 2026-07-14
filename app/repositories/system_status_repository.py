from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.system_status import SystemStatus
from app.repositories.base import BaseRepository


class SystemStatusRepository(BaseRepository[SystemStatus]):
    def __init__(self):
        super().__init__(SystemStatus)

    def get_current(self, db: Session) -> SystemStatus | None:
        statement = select(SystemStatus).order_by(SystemStatus.id.asc())
        return db.execute(statement).scalars().first()


system_status_repository = SystemStatusRepository()