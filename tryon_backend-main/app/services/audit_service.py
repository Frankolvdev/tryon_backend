from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.repositories.audit_log_repository import audit_log_repository


class AuditService:
    def create_log(
        self,
        db: Session,
        *,
        actor_user_id: int | None,
        action: str,
        entity_type: str | None = None,
        entity_id: str | None = None,
        description: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AuditLog:
        return audit_log_repository.create(
            db,
            data={
                "actor_user_id": actor_user_id,
                "action": action,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "description": description,
                "ip_address": ip_address,
                "user_agent": user_agent,
            },
        )

    def list_logs(
        self,
        db: Session,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> list[AuditLog]:
        return audit_log_repository.list_all(
            db,
            skip=skip,
            limit=limit,
        )


audit_service = AuditService()