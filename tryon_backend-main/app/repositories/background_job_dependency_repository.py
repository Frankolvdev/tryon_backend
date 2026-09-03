from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.background_job_dependency import (
    BackgroundJobDependency,
)
from app.repositories.base import BaseRepository


class BackgroundJobDependencyRepository(
    BaseRepository[BackgroundJobDependency]
):
    def __init__(self):
        super().__init__(BackgroundJobDependency)

    def list_by_job_id(
        self,
        db: Session,
        *,
        background_job_id: int,
    ) -> list[BackgroundJobDependency]:
        statement = (
            select(BackgroundJobDependency)
            .where(
                BackgroundJobDependency.background_job_id
                == background_job_id
            )
            .order_by(
                BackgroundJobDependency.id.asc()
            )
        )

        return list(
            db.execute(statement).scalars().all()
        )

    def list_dependents(
        self,
        db: Session,
        *,
        depends_on_job_id: int,
    ) -> list[BackgroundJobDependency]:
        statement = (
            select(BackgroundJobDependency)
            .where(
                BackgroundJobDependency.depends_on_job_id
                == depends_on_job_id
            )
            .order_by(
                BackgroundJobDependency.id.asc()
            )
        )

        return list(
            db.execute(statement).scalars().all()
        )

    def dependency_exists(
        self,
        db: Session,
        *,
        background_job_id: int,
        depends_on_job_id: int,
    ) -> bool:
        statement = select(
            BackgroundJobDependency.id
        ).where(
            BackgroundJobDependency.background_job_id
            == background_job_id,
            BackgroundJobDependency.depends_on_job_id
            == depends_on_job_id,
        )

        return (
            db.execute(statement).scalar_one_or_none()
            is not None
        )

    def delete_by_job_id(
        self,
        db: Session,
        *,
        background_job_id: int,
    ) -> int:
        dependencies = self.list_by_job_id(
            db,
            background_job_id=background_job_id,
        )

        for dependency in dependencies:
            db.delete(dependency)

        db.commit()

        return len(dependencies)


background_job_dependency_repository = (
    BackgroundJobDependencyRepository()
)