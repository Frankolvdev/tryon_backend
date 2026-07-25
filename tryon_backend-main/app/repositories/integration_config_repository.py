from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.integration_config import IntegrationConfig
from app.repositories.base import BaseRepository


class IntegrationConfigRepository(BaseRepository[IntegrationConfig]):
    def __init__(self):
        super().__init__(IntegrationConfig)

    def get_by_provider(
        self,
        db: Session,
        provider: str,
    ) -> IntegrationConfig | None:
        statement = select(IntegrationConfig).where(IntegrationConfig.provider == provider)
        return db.execute(statement).scalar_one_or_none()

    def list_all(
        self,
        db: Session,
    ) -> list[IntegrationConfig]:
        statement = select(IntegrationConfig).order_by(IntegrationConfig.provider.asc())
        return list(db.execute(statement).scalars().all())


integration_config_repository = IntegrationConfigRepository()