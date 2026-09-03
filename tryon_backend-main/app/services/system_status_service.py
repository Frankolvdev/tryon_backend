from sqlalchemy.orm import Session

from app.models.system_status import SystemStatus
from app.models.user import User
from app.repositories.system_status_repository import system_status_repository
from app.schemas.system_status import SystemStatusUpdate


class SystemStatusService:
    def get_or_create_status(self, db: Session) -> SystemStatus:
        status = system_status_repository.get_current(db)

        if status:
            return status

        return system_status_repository.create(
            db,
            data={
                "maintenance_mode": False,
                "registration_enabled": True,
                "tryon_enabled": True,
                "public_message": None,
                "internal_message": None,
                "updated_by_user_id": None,
            },
        )

    def get_public_status(self, db: Session) -> SystemStatus:
        return self.get_or_create_status(db)

    def update_status(
        self,
        db: Session,
        *,
        data: SystemStatusUpdate,
        admin_user: User,
    ) -> SystemStatus:
        status = self.get_or_create_status(db)

        update_data = data.model_dump(exclude_unset=True)
        update_data["updated_by_user_id"] = admin_user.id

        return system_status_repository.update(
            db,
            db_obj=status,
            data=update_data,
        )


system_status_service = SystemStatusService()