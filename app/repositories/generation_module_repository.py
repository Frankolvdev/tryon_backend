from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.generation_module import GenerationModule
from app.repositories.base import BaseRepository


class GenerationModuleRepository(BaseRepository[GenerationModule]):
    def __init__(self):
        super().__init__(GenerationModule)

    @staticmethod
    def _with_children(statement):
        return statement.options(
            selectinload(GenerationModule.inputs),
            selectinload(GenerationModule.outputs),
            selectinload(GenerationModule.steps),
        )

    def get_by_id_with_children(
        self, db: Session, module_id: int
    ) -> GenerationModule | None:
        statement = self._with_children(
            select(GenerationModule).where(GenerationModule.id == module_id)
        )
        return db.execute(statement).scalar_one_or_none()

    def get_by_key_and_version(
        self, db: Session, *, key: str, version: int
    ) -> GenerationModule | None:
        statement = self._with_children(
            select(GenerationModule).where(
                GenerationModule.key == key,
                GenerationModule.version == version,
            )
        )
        return db.execute(statement).scalar_one_or_none()

    def list_filtered(
        self,
        db: Session,
        *,
        key: str | None = None,
        category: str | None = None,
        engine: str | None = None,
        is_active: bool | None = None,
        search: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[GenerationModule]:
        statement = select(GenerationModule)
        if key is not None:
            statement = statement.where(GenerationModule.key == key)
        if category is not None:
            statement = statement.where(GenerationModule.category == category)
        if engine is not None:
            statement = statement.where(
                GenerationModule.default_execution_engine == engine
            )
        if is_active is not None:
            statement = statement.where(GenerationModule.is_active.is_(is_active))
        if search:
            pattern = f"%{search.strip()}%"
            statement = statement.where(
                or_(
                    GenerationModule.key.ilike(pattern),
                    GenerationModule.name.ilike(pattern),
                    GenerationModule.description.ilike(pattern),
                )
            )
        statement = self._with_children(
            statement.order_by(
                GenerationModule.key.asc(), GenerationModule.version.desc()
            )
            .offset(skip)
            .limit(limit)
        )
        return list(db.execute(statement).scalars().unique().all())

    def count_filtered(
        self,
        db: Session,
        *,
        key: str | None = None,
        category: str | None = None,
        engine: str | None = None,
        is_active: bool | None = None,
        search: str | None = None,
    ) -> int:
        statement = select(func.count(GenerationModule.id))
        if key is not None:
            statement = statement.where(GenerationModule.key == key)
        if category is not None:
            statement = statement.where(GenerationModule.category == category)
        if engine is not None:
            statement = statement.where(
                GenerationModule.default_execution_engine == engine
            )
        if is_active is not None:
            statement = statement.where(GenerationModule.is_active.is_(is_active))
        if search:
            pattern = f"%{search.strip()}%"
            statement = statement.where(
                or_(
                    GenerationModule.key.ilike(pattern),
                    GenerationModule.name.ilike(pattern),
                    GenerationModule.description.ilike(pattern),
                )
            )
        return int(db.execute(statement).scalar_one())


generation_module_repository = GenerationModuleRepository()
