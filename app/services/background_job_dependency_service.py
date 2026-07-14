from sqlalchemy.orm import Session

from app.common.job_enums import (
    JobDependencyType,
    JobStatus,
)
from app.models.background_job import BackgroundJob
from app.repositories.background_job_dependency_repository import (
    background_job_dependency_repository,
)
from app.repositories.background_job_repository import (
    background_job_repository,
)


class BackgroundJobDependencyService:
    TERMINAL_STATUSES = {
        JobStatus.SUCCEEDED.value,
        JobStatus.FAILED.value,
        JobStatus.CANCELED.value,
        JobStatus.TIMED_OUT.value,
        JobStatus.DEAD_LETTER.value,
    }

    FAILURE_STATUSES = {
        JobStatus.FAILED.value,
        JobStatus.CANCELED.value,
        JobStatus.TIMED_OUT.value,
        JobStatus.DEAD_LETTER.value,
    }

    def evaluate(
        self,
        db: Session,
        *,
        job: BackgroundJob,
    ) -> tuple[bool, bool, str | None]:
        """
        Returns:
        - ready: all dependencies are satisfied;
        - impossible: a required-success dependency has permanently failed;
        - reason: explanation when not ready.
        """

        dependencies = (
            background_job_dependency_repository
            .list_by_job_id(
                db,
                background_job_id=job.id,
            )
        )

        if not dependencies:
            return True, False, None

        for dependency in dependencies:
            dependency_job = (
                background_job_repository.get_by_id(
                    db,
                    dependency.depends_on_job_id,
                )
            )

            if not dependency_job:
                return (
                    False,
                    True,
                    (
                        "Dependency job "
                        f"{dependency.depends_on_job_id} "
                        "does not exist."
                    ),
                )

            if (
                dependency.dependency_type
                == JobDependencyType.SUCCESS.value
            ):
                if (
                    dependency_job.status
                    == JobStatus.SUCCEEDED.value
                ):
                    continue

                if (
                    dependency_job.status
                    in self.FAILURE_STATUSES
                ):
                    return (
                        False,
                        True,
                        (
                            "Required-success dependency "
                            f"{dependency_job.id} ended with "
                            f"status {dependency_job.status}."
                        ),
                    )

                return (
                    False,
                    False,
                    (
                        "Waiting for dependency "
                        f"{dependency_job.id} to succeed."
                    ),
                )

            if (
                dependency.dependency_type
                == JobDependencyType.COMPLETION.value
            ):
                if (
                    dependency_job.status
                    in self.TERMINAL_STATUSES
                ):
                    continue

                return (
                    False,
                    False,
                    (
                        "Waiting for dependency "
                        f"{dependency_job.id} to finish."
                    ),
                )

        return True, False, None


background_job_dependency_service = (
    BackgroundJobDependencyService()
)