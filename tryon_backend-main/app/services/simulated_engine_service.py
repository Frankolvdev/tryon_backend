import random
import time

from sqlalchemy.orm import Session

from app.common.enums import TryOnJobStatus
from app.common.exceptions import ConflictException, NotFoundException
from app.common.time import utc_now
from app.models.tryon_job import TryOnJob
from app.repositories.storage_file_repository import storage_file_repository
from app.repositories.system_setting_repository import system_setting_repository
from app.repositories.tryon_job_repository import tryon_job_repository
from app.schemas.simulated_engine import (
    SimulatedEngineSettingsResponse,
    SimulatedEngineSettingsUpdate,
    SimulatedEngineTestResponse,
)
from app.services.default_settings_service import default_settings_service
from app.services.storage_service import storage_service


KEYS = {
    "enabled": "simulated_engine_enabled",
    "execution_mode": "ai_execution_mode",
    "delay_seconds": "simulated_delay_seconds",
    "failure_rate_percent": "simulated_failure_rate_percent",
    "copy_person_image_as_result": "simulated_copy_person_image_as_result",
}


class SimulatedEngineService:
    def _setting(self, db: Session, name: str):
        return system_setting_repository.get_by_key(db, KEYS[name])

    def _ensure_settings(self, db: Session) -> None:
        missing = [
            key
            for key in KEYS.values()
            if system_setting_repository.get_by_key(db, key) is None
        ]
        if not missing:
            return

        default_settings_service.seed_defaults(db)
        db.flush()

        unresolved = [
            key
            for key in missing
            if system_setting_repository.get_by_key(db, key) is None
        ]
        if unresolved:
            raise NotFoundException(
                "Unable to initialize simulated engine settings: "
                + ", ".join(unresolved)
            )

    def get_settings(self, db: Session) -> SimulatedEngineSettingsResponse:
        self._ensure_settings(db)
        enabled = self._setting(db, "enabled")
        mode = self._setting(db, "execution_mode")
        delay = self._setting(db, "delay_seconds")
        failure = self._setting(db, "failure_rate_percent")
        copy_result = self._setting(db, "copy_person_image_as_result")
        return SimulatedEngineSettingsResponse(
            enabled=bool(enabled.value_boolean) if enabled else True,
            execution_mode=str(mode.value_string) if mode and mode.value_string else "simulated",
            delay_seconds=float(delay.value_float) if delay and delay.value_float is not None else 0.5,
            failure_rate_percent=float(failure.value_float) if failure and failure.value_float is not None else 0.0,
            copy_person_image_as_result=(bool(copy_result.value_boolean) if copy_result else True),
        )

    def update_settings(self, db: Session, data: SimulatedEngineSettingsUpdate) -> SimulatedEngineSettingsResponse:
        self._ensure_settings(db)
        values = {
            "enabled": {"value_boolean": data.enabled},
            "execution_mode": {"value_string": data.execution_mode},
            "delay_seconds": {"value_float": data.delay_seconds},
            "failure_rate_percent": {"value_float": data.failure_rate_percent},
            "copy_person_image_as_result": {"value_boolean": data.copy_person_image_as_result},
        }
        for name, payload in values.items():
            setting = self._setting(db, name)
            if setting is None:
                raise NotFoundException(
                    f"Simulated engine setting is unavailable: {KEYS[name]}"
                )
            system_setting_repository.update(db, db_obj=setting, data=payload)
        return self.get_settings(db)

    def test(self, db: Session) -> SimulatedEngineTestResponse:
        settings = self.get_settings(db)
        return SimulatedEngineTestResponse(
            available=settings.enabled, provider="simulated", status="READY" if settings.enabled else "DISABLED",
            delay_seconds=settings.delay_seconds, failure_rate_percent=settings.failure_rate_percent,
        )

    def process_job(self, db: Session, *, job_id: int) -> TryOnJob:
        job = tryon_job_repository.get_by_id(db, job_id)
        if not job:
            raise NotFoundException("Try-on job not found.")
        settings = self.get_settings(db)
        if not settings.enabled:
            raise ConflictException("Simulated engine is disabled.")
        job.status = TryOnJobStatus.PROCESSING.value
        db.add(job); db.commit(); db.refresh(job)
        if settings.delay_seconds:
            time.sleep(min(settings.delay_seconds, 30.0))
        if random.random() * 100 < settings.failure_rate_percent:
            job.status = TryOnJobStatus.FAILED.value
            job.error_message = "Simulated provider failure."
            db.add(job); db.commit(); db.refresh(job)
            return job
        person_file = storage_file_repository.get_by_id(db, job.person_image_file_id)
        if not person_file:
            job.status = TryOnJobStatus.FAILED.value
            job.error_message = "Person image file not found."
            db.add(job); db.commit(); db.refresh(job)
            return job
        if settings.copy_person_image_as_result:
            result_file = storage_service.create_local_copy_result(
                db=db, user_id=job.user_id, source_file=person_file, folder="tryon-results",
            )
            job.result_file_id = result_file.id
        job.status = TryOnJobStatus.COMPLETED.value
        job.completed_at = utc_now()
        job.actual_gpu_seconds = 0
        job.actual_gpu_cost_cents = 0
        job.error_message = None
        db.add(job); db.commit(); db.refresh(job)
        return job


simulated_engine_service = SimulatedEngineService()
