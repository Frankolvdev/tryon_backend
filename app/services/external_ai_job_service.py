import json
from typing import Any

from sqlalchemy.orm import Session

from app.common.time import utc_now
from app.models.external_ai_job import ExternalAiJob
from app.repositories.external_ai_job_repository import external_ai_job_repository
from app.repositories.runpod_config_repository import runpod_config_repository
from app.schemas.runpod_external import (
    ExternalAiJobResponse,
    RunPodCallbackRequest,
    RunPodCallbackResponse,
    RunPodCancelResponse,
    RunPodStatusResponse,
    RunPodSubmitRequest,
    RunPodSubmitResponse,
)
from app.services.runpod_client_service import runpod_client_service


class ExternalAiJobService:
    def _json(self, value: Any) -> str:
        return json.dumps(value or {}, ensure_ascii=False, default=str)

    def _parse(self, value: str | None) -> dict[str, Any] | None:
        if not value:
            return None

        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {"value": parsed}
        except json.JSONDecodeError:
            return {"raw": value}

    def _is_finished_status(self, status: str) -> bool:
        return status.lower() in [
            "completed",
            "failed",
            "cancelled",
            "canceled",
            "timed_out",
            "timeout",
        ]

    def _to_response(self, job: ExternalAiJob) -> ExternalAiJobResponse:
        return ExternalAiJobResponse(
            id=job.id,
            provider=job.provider,
            provider_job_id=job.provider_job_id,
            internal_job_type=job.internal_job_type,
            internal_job_id=job.internal_job_id,
            status=job.status,
            request=self._parse(job.request_json),
            response=self._parse(job.response_json),
            result=self._parse(job.result_json),
            error_message=job.error_message,
            started_at=job.started_at,
            finished_at=job.finished_at,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )

    def list_jobs(
        self,
        db: Session,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> list[ExternalAiJobResponse]:
        jobs = external_ai_job_repository.list_all(db, skip=skip, limit=limit)
        return [self._to_response(job) for job in jobs]

    def submit_runpod_job(
        self,
        db: Session,
        *,
        data: RunPodSubmitRequest,
    ) -> RunPodSubmitResponse:
        job = external_ai_job_repository.create(
            db,
            data={
                "provider": "runpod",
                "internal_job_type": data.internal_job_type,
                "internal_job_id": data.internal_job_id,
                "status": "submitting",
                "request_json": self._json(
                    {
                        "endpoint_id": data.endpoint_id,
                        "input": data.input,
                    }
                ),
                "started_at": utc_now(),
            },
        )

        try:
            response = runpod_client_service.submit_job(
                db,
                endpoint_id=data.endpoint_id,
                input_payload=data.input,
            )

            provider_job_id = response.get("id") or response.get("jobId")

            job.provider_job_id = provider_job_id
            job.status = response.get("status") or "submitted"
            job.response_json = self._json(response)

            db.add(job)
            db.commit()
            db.refresh(job)

            return RunPodSubmitResponse(
                external_ai_job_id=job.id,
                provider_job_id=provider_job_id,
                status=job.status,
                raw_response=response,
            )

        except Exception as error:
            job.status = "failed"
            job.error_message = str(error)
            job.finished_at = utc_now()

            db.add(job)
            db.commit()
            db.refresh(job)

            raise

    def refresh_runpod_status(
        self,
        db: Session,
        *,
        external_ai_job_id: int,
        endpoint_id: str,
    ) -> RunPodStatusResponse:
        job = external_ai_job_repository.get_by_id(db, external_ai_job_id)

        if not job:
            from app.common.exceptions import NotFoundException

            raise NotFoundException("External AI job not found.")

        if not job.provider_job_id:
            return RunPodStatusResponse(
                external_ai_job_id=job.id,
                provider_job_id=None,
                status=job.status,
                raw_response=self._parse(job.response_json),
                result=self._parse(job.result_json),
                error_message=job.error_message,
            )

        response = runpod_client_service.get_status(
            db,
            endpoint_id=endpoint_id,
            provider_job_id=job.provider_job_id,
        )

        status = response.get("status") or job.status
        job.status = status
        job.response_json = self._json(response)

        if "output" in response:
            job.result_json = self._json(response.get("output"))

        if self._is_finished_status(status):
            job.finished_at = utc_now()

        db.add(job)
        db.commit()
        db.refresh(job)

        if job.internal_job_type == "tryon" and job.internal_job_id:
            from app.services.tryon_result_service import tryon_result_service

            tryon_result_service.apply_runpod_result_to_tryon_job(
                db=db,
                tryon_job_id=job.internal_job_id,
                runpod_status=status,
                output=response.get("output") or {},
                error_message=response.get("error"),
                execution_time_ms=response.get("executionTime"),
            )

        return RunPodStatusResponse(
            external_ai_job_id=job.id,
            provider_job_id=job.provider_job_id,
            status=job.status,
            raw_response=response,
            result=self._parse(job.result_json),
            error_message=job.error_message,
        )

    def cancel_runpod_job(
        self,
        db: Session,
        *,
        external_ai_job_id: int,
        endpoint_id: str,
    ) -> RunPodCancelResponse:
        job = external_ai_job_repository.get_by_id(db, external_ai_job_id)

        if not job:
            from app.common.exceptions import NotFoundException

            raise NotFoundException("External AI job not found.")

        if not job.provider_job_id:
            job.status = "canceled"
            job.finished_at = utc_now()
            db.add(job)
            db.commit()
            db.refresh(job)

            return RunPodCancelResponse(
                external_ai_job_id=job.id,
                provider_job_id=None,
                status=job.status,
                raw_response=None,
            )

        response = runpod_client_service.cancel_job(
            db,
            endpoint_id=endpoint_id,
            provider_job_id=job.provider_job_id,
        )

        job.status = response.get("status") or "canceled"
        job.response_json = self._json(response)
        job.finished_at = utc_now()

        db.add(job)
        db.commit()
        db.refresh(job)

        if job.internal_job_type == "tryon" and job.internal_job_id:
            from app.services.tryon_result_service import tryon_result_service

            tryon_result_service.apply_runpod_result_to_tryon_job(
                db=db,
                tryon_job_id=job.internal_job_id,
                runpod_status="canceled",
                output={},
                error_message="RunPod job canceled by admin.",
                execution_time_ms=None,
            )

        return RunPodCancelResponse(
            external_ai_job_id=job.id,
            provider_job_id=job.provider_job_id,
            status=job.status,
            raw_response=response,
        )

    def process_runpod_callback(
        self,
        db: Session,
        *,
        data: RunPodCallbackRequest,
    ) -> RunPodCallbackResponse:
        provider_job_id = data.id

        if not provider_job_id:
            return RunPodCallbackResponse(
                received=False,
                provider_job_id=None,
                status=data.status,
                message="Missing RunPod job id.",
            )

        job = external_ai_job_repository.get_by_provider_job_id(
            db,
            provider="runpod",
            provider_job_id=provider_job_id,
        )

        if not job:
            return RunPodCallbackResponse(
                received=False,
                provider_job_id=provider_job_id,
                status=data.status,
                message="External AI job not found.",
            )

        job.status = data.status
        job.result_json = self._json(data.output)
        job.error_message = data.error

        if self._is_finished_status(data.status):
            job.finished_at = utc_now()

        db.add(job)
        db.commit()
        db.refresh(job)

        if job.internal_job_type == "tryon" and job.internal_job_id:
            from app.services.tryon_result_service import tryon_result_service

            tryon_result_service.apply_runpod_result_to_tryon_job(
                db=db,
                tryon_job_id=job.internal_job_id,
                runpod_status=data.status,
                output=data.output or {},
                error_message=data.error,
                execution_time_ms=data.executionTime,
            )

        return RunPodCallbackResponse(
            received=True,
            provider_job_id=provider_job_id,
            status=data.status,
            message="RunPod callback processed successfully.",
        )

    def poll_pending_runpod_jobs(
        self,
        db: Session,
        *,
        limit: int = 50,
    ) -> dict:
        pending_jobs = external_ai_job_repository.list_pending_runpod_jobs(
            db,
            limit=limit,
        )

        active_runpod_config = runpod_config_repository.get_active(db)

        if not active_runpod_config or not active_runpod_config.endpoint_id:
            return {
                "processed": 0,
                "failed": 0,
                "skipped": len(pending_jobs),
                "message": "No active RunPod config with endpoint_id.",
            }

        processed = 0
        failed = 0

        for job in pending_jobs:
            try:
                self.refresh_runpod_status(
                    db=db,
                    external_ai_job_id=job.id,
                    endpoint_id=active_runpod_config.endpoint_id,
                )
                processed += 1
            except Exception as error:
                job.error_message = str(error)
                db.add(job)
                db.commit()
                failed += 1

        return {
            "processed": processed,
            "failed": failed,
            "skipped": 0,
            "message": "Pending RunPod jobs processed.",
        }


external_ai_job_service = ExternalAiJobService()