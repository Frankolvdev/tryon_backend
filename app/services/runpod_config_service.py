from sqlalchemy.orm import Session

from app.common.exceptions import NotFoundException
from app.models.runpod_config import RunPodConfig
from app.repositories.runpod_config_repository import runpod_config_repository
from app.schemas.runpod import RunPodConfigCreate, RunPodConfigUpdate


class RunPodConfigService:
    def get_active_config(self, db: Session) -> RunPodConfig | None:
        return runpod_config_repository.get_active(db)

    def list_configs(self, db: Session) -> list[RunPodConfig]:
        return runpod_config_repository.list_all(db)

    def create_config(
        self,
        db: Session,
        data: RunPodConfigCreate,
    ) -> RunPodConfig:
        return runpod_config_repository.create(
            db,
            data=data.model_dump(),
        )

    def update_config(
        self,
        db: Session,
        config_id: int,
        data: RunPodConfigUpdate,
    ) -> RunPodConfig:
        config = runpod_config_repository.get_by_id(db, config_id)

        if not config:
            raise NotFoundException("RunPod config not found.")

        return runpod_config_repository.update(
            db,
            db_obj=config,
            data=data.model_dump(exclude_unset=True),
        )


runpod_config_service = RunPodConfigService()