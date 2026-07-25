from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.workflow_definition import (
    WorkflowDefinition,
)
from app.repositories.base import BaseRepository


class WorkflowDefinitionRepository(
    BaseRepository[WorkflowDefinition]
):
    def __init__(self):
        super().__init__(WorkflowDefinition)

    def get_by_key_and_version(
        self,
        db: Session,
        *,
        key: str,
        version: int,
    ) -> WorkflowDefinition | None:
        statement = select(
            WorkflowDefinition
        ).where(
            WorkflowDefinition.key == key,
            WorkflowDefinition.version == version,
        )

        return db.execute(
            statement
        ).scalar_one_or_none()

    def get_latest_by_key(
        self,
        db: Session,
        *,
        key: str,
        active_only: bool = False,
    ) -> WorkflowDefinition | None:
        statement = select(
            WorkflowDefinition
        ).where(
            WorkflowDefinition.key == key
        )

        if active_only:
            statement = statement.where(
                WorkflowDefinition.is_active.is_(True)
            )

        statement = (
            statement
            .order_by(
                WorkflowDefinition.version.desc()
            )
            .limit(1)
        )

        return db.execute(
            statement
        ).scalar_one_or_none()

    def get_default(
        self,
        db: Session,
        *,
        category: str,
    ) -> WorkflowDefinition | None:
        statement = (
            select(WorkflowDefinition)
            .where(
                WorkflowDefinition.category == category,
                WorkflowDefinition.is_active.is_(True),
                WorkflowDefinition.is_default.is_(True),
            )
            .order_by(
                WorkflowDefinition.version.desc()
            )
            .limit(1)
        )

        return db.execute(
            statement
        ).scalar_one_or_none()

    def list_filtered(
        self,
        db: Session,
        *,
        key: str | None = None,
        category: str | None = None,
        is_active: bool | None = None,
        is_default: bool | None = None,
        search: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[WorkflowDefinition]:
        statement = select(
            WorkflowDefinition
        )

        if key is not None:
            statement = statement.where(
                WorkflowDefinition.key == key
            )

        if category is not None:
            statement = statement.where(
                WorkflowDefinition.category
                == category
            )

        if is_active is not None:
            statement = statement.where(
                WorkflowDefinition.is_active.is_(
                    is_active
                )
            )

        if is_default is not None:
            statement = statement.where(
                WorkflowDefinition.is_default.is_(
                    is_default
                )
            )

        if search:
            pattern = f"%{search.strip()}%"

            statement = statement.where(
                or_(
                    WorkflowDefinition.key.ilike(
                        pattern
                    ),
                    WorkflowDefinition.name.ilike(
                        pattern
                    ),
                    WorkflowDefinition.description.ilike(
                        pattern
                    ),
                )
            )

        statement = (
            statement
            .order_by(
                WorkflowDefinition.key.asc(),
                WorkflowDefinition.version.desc(),
            )
            .offset(skip)
            .limit(limit)
        )

        return list(
            db.execute(
                statement
            ).scalars().all()
        )

    def count_filtered(
        self,
        db: Session,
        *,
        key: str | None = None,
        category: str | None = None,
        is_active: bool | None = None,
        is_default: bool | None = None,
        search: str | None = None,
    ) -> int:
        statement = select(
            func.count(
                WorkflowDefinition.id
            )
        )

        if key is not None:
            statement = statement.where(
                WorkflowDefinition.key == key
            )

        if category is not None:
            statement = statement.where(
                WorkflowDefinition.category
                == category
            )

        if is_active is not None:
            statement = statement.where(
                WorkflowDefinition.is_active.is_(
                    is_active
                )
            )

        if is_default is not None:
            statement = statement.where(
                WorkflowDefinition.is_default.is_(
                    is_default
                )
            )

        if search:
            pattern = f"%{search.strip()}%"

            statement = statement.where(
                or_(
                    WorkflowDefinition.key.ilike(
                        pattern
                    ),
                    WorkflowDefinition.name.ilike(
                        pattern
                    ),
                    WorkflowDefinition.description.ilike(
                        pattern
                    ),
                )
            )

        return int(
            db.execute(
                statement
            ).scalar_one()
        )

    def list_defaults_for_category(
        self,
        db: Session,
        *,
        category: str,
    ) -> list[WorkflowDefinition]:
        statement = select(
            WorkflowDefinition
        ).where(
            WorkflowDefinition.category == category,
            WorkflowDefinition.is_default.is_(True),
        )

        return list(
            db.execute(
                statement
            ).scalars().all()
        )


workflow_definition_repository = (
    WorkflowDefinitionRepository()
)