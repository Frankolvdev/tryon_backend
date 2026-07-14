from sqlalchemy.orm import Session

from app.models.activity_log import ActivityLog
from app.repositories.activity_log_repository import activity_log_repository


class ActivityService:
    def create_log(
        self,
        db: Session,
        *,
        user_id: int | None,
        action: str,
        description: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> ActivityLog:
        return activity_log_repository.create(
            db,
            data={
                "user_id": user_id,
                "action": action,
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
    ) -> list[ActivityLog]:
        return activity_log_repository.list_all(
            db,
            skip=skip,
            limit=limit,
        )

    def list_user_logs(
        self,
        db: Session,
        *,
        user_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> list[ActivityLog]:
        return activity_log_repository.list_by_user_id(
            db,
            user_id,
            skip=skip,
            limit=limit,
        )


activity_service = ActivityService()