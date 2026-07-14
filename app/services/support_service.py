from sqlalchemy.orm import Session

from app.common.enums import NotificationCategory
from app.common.exceptions import ForbiddenException, NotFoundException
from app.models.support_ticket import SupportTicket
from app.models.user import User
from app.repositories.support_ticket_repository import support_ticket_repository
from app.schemas.support import SupportTicketAdminUpdate, SupportTicketCreate
from app.services.notification_service import notification_service


class SupportService:
    def create_ticket(
        self,
        db: Session,
        *,
        user: User,
        data: SupportTicketCreate,
    ) -> SupportTicket:
        ticket = support_ticket_repository.create(
            db,
            data={
                "user_id": user.id,
                "subject": data.subject,
                "message": data.message,
            },
        )

        notification_service.info(
            db,
            title="New support ticket",
            message=f"User {user.email} created support ticket #{ticket.id}.",
            category=NotificationCategory.SYSTEM,
        )

        return ticket

    def list_my_tickets(
        self,
        db: Session,
        *,
        user: User,
        skip: int = 0,
        limit: int = 50,
    ) -> list[SupportTicket]:
        return support_ticket_repository.list_by_user_id(
            db,
            user.id,
            skip=skip,
            limit=limit,
        )

    def get_my_ticket(
        self,
        db: Session,
        *,
        user: User,
        ticket_id: int,
    ) -> SupportTicket:
        ticket = support_ticket_repository.get_by_id(db, ticket_id)

        if not ticket:
            raise NotFoundException("Support ticket not found.")

        if ticket.user_id != user.id:
            raise ForbiddenException("You do not have access to this ticket.")

        return ticket

    def admin_list_tickets(
        self,
        db: Session,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> list[SupportTicket]:
        return support_ticket_repository.list_all(
            db,
            skip=skip,
            limit=limit,
        )

    def admin_get_ticket(
        self,
        db: Session,
        ticket_id: int,
    ) -> SupportTicket:
        ticket = support_ticket_repository.get_by_id(db, ticket_id)

        if not ticket:
            raise NotFoundException("Support ticket not found.")

        return ticket

    def admin_update_ticket(
        self,
        db: Session,
        *,
        ticket_id: int,
        data: SupportTicketAdminUpdate,
    ) -> SupportTicket:
        ticket = self.admin_get_ticket(db, ticket_id)

        return support_ticket_repository.update(
            db,
            db_obj=ticket,
            data=data.model_dump(exclude_unset=True),
        )


support_service = SupportService()