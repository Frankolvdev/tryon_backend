from sqlalchemy.orm import Session

from app.common.enums import TryOnJobStatus
from app.common.time import utc_now
from app.repositories.tryon_job_repository import tryon_job_repository
from app.services.storage_service import storage_service


class TryOnResultService:
    def apply_runpod_result_to_tryon_job(
        self,
        db: Session,
        *,
        tryon_job_id: int,
        runpod_status: str,
        output: dict,
        error_message: str | None = None,
        execution_time_ms: int | None = None,
    ):
        job = tryon_job_repository.get_by_id(db, tryon_job_id)

        if not job:
            return None

        normalized_status = runpod_status.lower()

        if normalized_status in ["cancelled", "canceled"]:
            job.status = TryOnJobStatus.CANCELED.value
            job.error_message = error_message or "RunPod job was canceled."

            db.add(job)
            db.commit()
            db.refresh(job)

            return job

        if normalized_status in ["failed", "timed_out", "timeout"]:
            job.status = TryOnJobStatus.FAILED.value
            job.error_message = error_message or "RunPod job failed."

            db.add(job)
            db.commit()
            db.refresh(job)

            return job

        if normalized_status not in ["completed", "success"]:
            job.status = TryOnJobStatus.PROCESSING.value
            db.add(job)
            db.commit()
            db.refresh(job)

            return job

        result_url = (
            output.get("result_url")
            or output.get("image_url")
            or output.get("output_url")
            or output.get("result")
        )

        if not result_url:
            job.status = TryOnJobStatus.FAILED.value
            job.error_message = "RunPod completed but did not return a result URL."

            db.add(job)
            db.commit()
            db.refresh(job)

            return job

        result_file = storage_service.create_remote_result_record(
            db=db,
            user_id=job.user_id,
            public_url=result_url,
            folder="tryon-results",
            original_filename=f"tryon-result-{job.id}.jpg",
            content_type="image/jpeg",
        )

        job.result_file_id = result_file.id
        job.status = TryOnJobStatus.COMPLETED.value
        job.completed_at = utc_now()

        if execution_time_ms is not None:
            job.actual_gpu_seconds = max(1, int(execution_time_ms / 1000))

        if job.actual_gpu_cost_cents is None:
            job.actual_gpu_cost_cents = job.estimated_gpu_cost_cents

        db.add(job)
        db.commit()
        db.refresh(job)

        return job


tryon_result_service = TryOnResultService()