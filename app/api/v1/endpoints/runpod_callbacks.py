import hmac
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Request,
)
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.common.job_enums import JobStatus
from app.repositories.background_job_repository import (
    background_job_repository,
)
from app.services.background_job_redis_service import (
    background_job_redis_service,
)
from app.services.runpod_runtime_config_service import (
    runpod_runtime_config_service,
)


router = APIRouter()


class RunPodCallbackPayload(BaseModel):
    id: str | None = None
    status: str | None = None

    output: Any | None = None
    error: Any | None = None

    executionTime: float | None = None
    delayTime: float | None = None


def _validate_callback_secret(
    *,
    db: Session,
    received_secret: str | None,
) -> None:
    configured_secret = (
        runpod_runtime_config_service
        .callback_secret(db)
    )

    if not configured_secret:
        return

    if not received_secret:
        raise HTTPException(
            status_code=401,
            detail=(
                "RunPod callback secret "
                "is required."
            ),
        )

    if not hmac.compare_digest(
        received_secret,
        configured_secret,
    ):
        raise HTTPException(
            status_code=401,
            detail=(
                "Invalid RunPod callback secret."
            ),
        )


def _local_status(
    provider_status: str,
) -> str | None:
    mapping = {
        "IN_QUEUE": JobStatus.QUEUED.value,
        "IN_PROGRESS": JobStatus.RUNNING.value,
        "COMPLETED": JobStatus.SUCCEEDED.value,
        "FAILED": JobStatus.FAILED.value,
        "CANCELLED": JobStatus.CANCELED.value,
        "TIMED_OUT": JobStatus.TIMED_OUT.value,
    }

    return mapping.get(
        provider_status.upper()
    )


@router.post("/callback")
def receive_runpod_callback(
    data: RunPodCallbackPayload,
    request: Request,
    db: Session = Depends(get_db),
    x_runpod_callback_secret: str | None = Header(
        default=None,
        alias="X-RunPod-Callback-Secret",
    ),
):
    _validate_callback_secret(
        db=db,
        received_secret=(
            x_runpod_callback_secret
        ),
    )

    if not data.id:
        raise HTTPException(
            status_code=422,
            detail=(
                "RunPod callback does not "
                "contain a job ID."
            ),
        )

    provider_status = str(
        data.status or "UNKNOWN"
    ).upper()

    job = (
        background_job_repository
        .get_by_provider_job_id(
            db,
            data.id,
        )
    )

    if not job:
        return {
            "received": True,
            "matched": False,
            "provider_job_id": data.id,
            "provider_status": (
                provider_status
            ),
        }

    mapped_status = _local_status(
        provider_status
    )

    # The active worker remains responsible for completing attempts,
    # retries, result storage and clearing the lease. The callback
    # provides fast status notification without competing with it.
    if provider_status == "IN_PROGRESS":
        job.progress = max(
            job.progress,
            25.0,
        )

        job.progress_message = (
            "RunPod callback reports that "
            "the job is running."
        )

    elif provider_status == "IN_QUEUE":
        job.progress = max(
            job.progress,
            2.0,
        )

        job.progress_message = (
            "RunPod callback reports that "
            "the job is queued."
        )

    elif mapped_status:
        job.progress_message = (
            "RunPod callback received with "
            f"status {provider_status}."
        )

    db.add(job)
    db.commit()
    db.refresh(job)

    background_job_redis_service.publish_status(
        public_id=job.public_id,
        status=(
            mapped_status
            or job.status
        ),
        progress=job.progress,
        message=job.progress_message,
        metadata={
            "provider": (
                "runpod_serverless"
            ),
            "provider_job_id": data.id,
            "provider_status": (
                provider_status
            ),
            "execution_time": (
                data.executionTime
            ),
            "delay_time": data.delayTime,
        },
    )

    return {
        "received": True,
        "matched": True,
        "background_job_id": job.id,
        "public_id": job.public_id,
        "provider_job_id": data.id,
        "provider_status": provider_status,
        "client_ip": (
            request.client.host
            if request.client
            else None
        ),
    }


@router.get("/callback/health")
def runpod_callback_health(
    db: Session = Depends(get_db),
):
    return {
        "status": "ok",
        "provider": "runpod",
        "callback_ready": True,
        "secret_configured": bool(
            runpod_runtime_config_service
            .callback_secret(db)
        ),
    }