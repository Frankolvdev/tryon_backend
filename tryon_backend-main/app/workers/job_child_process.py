import traceback
from multiprocessing.queues import Queue
from time import perf_counter
from typing import Any

from app.db.database import SessionLocal
from app.services.business_observability_service import (
    business_observability_service,
)
from app.services.comfyui_local_adapter_service import (
    comfyui_local_adapter_service,
)
from app.services.operational_event_service import (
    operational_event_service,
)
from app.services.runpod_serverless_adapter_service import (
    runpod_serverless_adapter_service,
)
from app.workers.handler_registry import (
    internal_job_handler_registry,
)


def execute_internal_job_child(
    result_queue: Queue,
    *,
    job_type: str,
    payload: dict[str, Any],
) -> None:
    started_at = perf_counter()
    db = SessionLocal()

    try:
        result = (
            internal_job_handler_registry.execute(
                db,
                job_type=job_type,
                payload=payload,
            )
        )

        duration_seconds = (
            perf_counter()
            - started_at
        )

        result_queue.put(
            {
                "success": True,
                "result": (
                    result
                    if isinstance(result, dict)
                    else {
                        "value": result,
                    }
                ),
                "metrics": {
                    "duration_seconds": (
                        duration_seconds
                    ),
                    "provider": "internal",
                },
            }
        )

    except Exception as error:
        db.rollback()

        operational_event_service.safe_create(
            db,
            event_type=(
                "internal_job_execution_failed"
            ),
            source="worker",
            severity="error",
            message=(
                f"Internal job '{job_type}' failed."
            ),
            exception=error,
            details={
                "job_type": job_type,
                "payload_keys": list(
                    payload.keys()
                ),
                "traceback": (
                    traceback.format_exc()
                ),
            },
        )

        result_queue.put(
            {
                "success": False,
                "error_code": (
                    error.__class__.__name__
                ),
                "error_message": str(error),
                "error_details": {
                    "traceback": (
                        traceback.format_exc()
                    ),
                },
                "metrics": {
                    "duration_seconds": (
                        perf_counter()
                        - started_at
                    ),
                    "provider": "internal",
                },
            }
        )

    finally:
        db.close()


def execute_comfyui_job_child(
    result_queue: Queue,
    *,
    prompt_id: str,
    client_id: str,
    job_public_id: str,
    timeout_seconds: int,
    download_outputs: bool,
) -> None:
    started_at = perf_counter()
    db = SessionLocal()

    try:
        result = (
            comfyui_local_adapter_service
            .execute_queued_prompt(
                prompt_id=prompt_id,
                client_id=client_id,
                job_public_id=job_public_id,
                timeout_seconds=timeout_seconds,
                download_outputs=(
                    download_outputs
                ),
            )
        )

        duration_seconds = (
            perf_counter()
            - started_at
        )

        business_observability_service.provider_operation(
            provider="comfyui_local",
            operation="execute_prompt",
            status="succeeded",
            duration_seconds=duration_seconds,
        )

        result_queue.put(
            {
                "success": True,
                "result": result,
                "metrics": {
                    "duration_seconds": (
                        duration_seconds
                    ),
                    "provider": (
                        "comfyui_local"
                    ),
                    "prompt_id": prompt_id,
                },
            }
        )

    except Exception as error:
        duration_seconds = (
            perf_counter()
            - started_at
        )

        business_observability_service.provider_operation(
            provider="comfyui_local",
            operation="execute_prompt",
            status="failed",
            duration_seconds=duration_seconds,
        )

        operational_event_service.safe_create(
            db,
            event_type=(
                "comfyui_execution_failed"
            ),
            source="comfyui",
            severity="error",
            message=(
                "Local ComfyUI execution failed."
            ),
            provider_job_id=prompt_id,
            exception=error,
            details={
                "prompt_id": prompt_id,
                "client_id": client_id,
                "job_public_id": (
                    job_public_id
                ),
                "traceback": (
                    traceback.format_exc()
                ),
            },
        )

        result_queue.put(
            {
                "success": False,
                "error_code": (
                    error.__class__.__name__
                ),
                "error_message": str(error),
                "error_details": {
                    "traceback": (
                        traceback.format_exc()
                    ),
                    "prompt_id": prompt_id,
                },
                "metrics": {
                    "duration_seconds": (
                        duration_seconds
                    ),
                    "provider": (
                        "comfyui_local"
                    ),
                },
            }
        )

    finally:
        db.close()


def execute_runpod_job_child(
    result_queue: Queue,
    *,
    provider_job_id: str,
    endpoint_id: str,
    job_public_id: str,
    timeout_seconds: int,
    download_outputs: bool,
) -> None:
    started_at = perf_counter()
    db = SessionLocal()

    try:
        result = (
            runpod_serverless_adapter_service
            .execute_submitted_job(
                db,
                provider_job_id=(
                    provider_job_id
                ),
                endpoint_id=endpoint_id,
                job_public_id=job_public_id,
                timeout_seconds=timeout_seconds,
                download_outputs=(
                    download_outputs
                ),
            )
        )

        duration_seconds = (
            perf_counter()
            - started_at
        )

        business_observability_service.provider_operation(
            provider="runpod_serverless",
            operation="execute_job",
            status="succeeded",
            duration_seconds=duration_seconds,
        )

        result_queue.put(
            {
                "success": True,
                "result": result,
                "metrics": {
                    "duration_seconds": (
                        duration_seconds
                    ),
                    "provider": (
                        "runpod_serverless"
                    ),
                    "provider_execution_time": (
                        result.get(
                            "execution_time"
                        )
                    ),
                    "provider_delay_time": (
                        result.get(
                            "delay_time"
                        )
                    ),
                    "endpoint_id": endpoint_id,
                },
            }
        )

    except Exception as error:
        db.rollback()

        duration_seconds = (
            perf_counter()
            - started_at
        )

        business_observability_service.provider_operation(
            provider="runpod_serverless",
            operation="execute_job",
            status="failed",
            duration_seconds=duration_seconds,
        )

        operational_event_service.safe_create(
            db,
            event_type=(
                "runpod_execution_failed"
            ),
            source="runpod",
            severity="error",
            message=(
                "RunPod Serverless execution failed."
            ),
            provider_job_id=provider_job_id,
            exception=error,
            details={
                "provider_job_id": (
                    provider_job_id
                ),
                "endpoint_id": endpoint_id,
                "job_public_id": (
                    job_public_id
                ),
                "traceback": (
                    traceback.format_exc()
                ),
            },
        )

        result_queue.put(
            {
                "success": False,
                "error_code": (
                    error.__class__.__name__
                ),
                "error_message": str(error),
                "error_details": {
                    "traceback": (
                        traceback.format_exc()
                    ),
                    "provider_job_id": (
                        provider_job_id
                    ),
                    "endpoint_id": endpoint_id,
                },
                "metrics": {
                    "duration_seconds": (
                        duration_seconds
                    ),
                    "provider": (
                        "runpod_serverless"
                    ),
                    "endpoint_id": endpoint_id,
                },
            }
        )

    finally:
        db.close()