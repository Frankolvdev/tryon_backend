from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.models.support_ticket import SupportTicket
from app.repositories.base import BaseRepository


class SupportTicketRepository(BaseRepository[SupportTicket]):
    def __init__(self):
        super().__init__(SupportTicket)

    def list_by_user_id(
        self,
        db: Session,
        user_id: int,
        *,
        skip: int = 0,
        limit: int = 50,
    ) -> list[SupportTicket]:
        statement = (
            select(SupportTicket)
            .where(SupportTicket.user_id == user_id)
            .order_by(SupportTicket.created_at.desc())
            .offset(skip)
            .limit(limit)
        )

        return list(db.execute(statement).scalars().all())

    def list_all(
        self,
        db: Session,
        *,
        skip: int = 0,
        limit: int = 100,
        status: str | None = None,
        priority: str | None = None,
        search: str | None = None,
    ) -> list[SupportTicket]:
        statement = select(SupportTicket)
        if status:
            statement = statement.where(SupportTicket.status == status)
        if priority:
            statement = statement.where(SupportTicket.priority == priority)
        if search and search.strip():
            term = f"%{search.strip()}%"
            statement = statement.where(or_(
                SupportTicket.subject.ilike(term),
                SupportTicket.message.ilike(term),
                SupportTicket.admin_notes.ilike(term),
            ))
        statement = (
            statement
            .order_by(SupportTicket.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(db.execute(statement).scalars().all())

    def count_all(
        self,
        db: Session,
        *,
        status: str | None = None,
        priority: str | None = None,
        search: str | None = None,
    ) -> int:
        statement = select(func.count(SupportTicket.id))
        if status:
            statement = statement.where(SupportTicket.status == status)
        if priority:
            statement = statement.where(SupportTicket.priority == priority)
        if search and search.strip():
            term = f"%{search.strip()}%"
            statement = statement.where(or_(
                SupportTicket.subject.ilike(term),
                SupportTicket.message.ilike(term),
                SupportTicket.admin_notes.ilike(term),
            ))
        return int(db.execute(statement).scalar_one())

    def admin_summary(self, db: Session) -> dict[str, int]:
        row = db.execute(
            select(
                func.count(SupportTicket.id),
                func.sum(case((SupportTicket.status == "open", 1), else_=0)),
                func.sum(case((SupportTicket.status == "in_progress", 1), else_=0)),
                func.sum(case((SupportTicket.status.in_(["resolved", "closed"]), 1), else_=0)),
                func.sum(case((SupportTicket.priority.in_(["urgent", "critical"]), 1), else_=0)),
            )
        ).one()
        return {
            "total": int(row[0] or 0),
            "open": int(row[1] or 0),
            "in_progress": int(row[2] or 0),
            "resolved": int(row[3] or 0),
            "urgent": int(row[4] or 0),
        }


support_ticket_repository = SupportTicketRepository()