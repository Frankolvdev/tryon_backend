from app.observability.metrics import (
    BACKGROUND_JOB_ATTEMPTS_TOTAL,
    BACKGROUND_JOB_COMPLETIONS_TOTAL,
    BACKGROUND_JOB_DURATION_SECONDS,
    RUNPOD_COMPLETIONS_TOTAL,
    RUNPOD_EXECUTION_DURATION_SECONDS,
    RUNPOD_QUEUE_DELAY_SECONDS,
    RUNPOD_SUBMISSIONS_TOTAL,
    WORKER_ACTIVE_JOBS,
    WORKER_ERRORS_TOTAL,
    WORKER_HEARTBEATS_TOTAL,
)


class WorkerMetricsService:
    def job_started(
        self,
        *,
        worker_name: str,
        queue_name: str,
        job_type: str,
        execution_mode: str,
    ) -> None:
        WORKER_ACTIVE_JOBS.labels(
            worker_name=worker_name,
            queue_name=queue_name,
        ).inc()

        BACKGROUND_JOB_ATTEMPTS_TOTAL.labels(
            queue_name=queue_name,
            job_type=job_type,
            execution_mode=execution_mode,
        ).inc()

    def heartbeat(
        self,
        *,
        worker_name: str,
        queue_name: str,
    ) -> None:
        WORKER_HEARTBEATS_TOTAL.labels(
            worker_name=worker_name,
            queue_name=queue_name,
        ).inc()

    def job_finished(
        self,
        *,
        worker_name: str,
        queue_name: str,
        job_type: str,
        execution_mode: str,
        status: str,
        duration_seconds: float,
    ) -> None:
        WORKER_ACTIVE_JOBS.labels(
            worker_name=worker_name,
            queue_name=queue_name,
        ).dec()

        BACKGROUND_JOB_COMPLETIONS_TOTAL.labels(
            queue_name=queue_name,
            job_type=job_type,
            execution_mode=execution_mode,
            status=status,
        ).inc()

        BACKGROUND_JOB_DURATION_SECONDS.labels(
            queue_name=queue_name,
            job_type=job_type,
            execution_mode=execution_mode,
            status=status,
        ).observe(
            max(
                float(duration_seconds),
                0.0,
            )
        )

    def worker_error(
        self,
        *,
        worker_name: str,
        queue_name: str,
        error_type: str,
    ) -> None:
        WORKER_ERRORS_TOTAL.labels(
            worker_name=worker_name,
            queue_name=queue_name,
            error_type=error_type,
        ).inc()

    def runpod_submitted(
        self,
        *,
        endpoint_id: str,
    ) -> None:
        RUNPOD_SUBMISSIONS_TOTAL.labels(
            endpoint_id=endpoint_id,
        ).inc()

    def runpod_completed(
        self,
        *,
        endpoint_id: str,
        status: str,
        execution_time_seconds: float | None,
        delay_time_seconds: float | None,
    ) -> None:
        RUNPOD_COMPLETIONS_TOTAL.labels(
            endpoint_id=endpoint_id,
            status=status,
        ).inc()

        if execution_time_seconds is not None:
            RUNPOD_EXECUTION_DURATION_SECONDS.labels(
                endpoint_id=endpoint_id,
            ).observe(
                max(
                    float(
                        execution_time_seconds
                    ),
                    0.0,
                )
            )

        if delay_time_seconds is not None:
            RUNPOD_QUEUE_DELAY_SECONDS.labels(
                endpoint_id=endpoint_id,
            ).observe(
                max(
                    float(
                        delay_time_seconds
                    ),
                    0.0,
                )
            )


worker_metrics_service = (
    WorkerMetricsService()
)