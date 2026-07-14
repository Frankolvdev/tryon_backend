import logging
import time
from datetime import datetime, timezone
from typing import Any

from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.redis_client import redis_client
from app.db.database import engine
from app.observability.metrics import (
    BACKGROUND_JOB_EXPIRED_LEASES,
    BACKGROUND_JOB_QUEUE_OLDEST_AGE_SECONDS,
    BACKGROUND_JOBS,
    OBSERVABILITY_COLLECTOR_ERRORS_TOTAL,
    POSTGRES_AVAILABLE,
    POSTGRES_HEALTH_CHECK_DURATION_SECONDS,
    POSTGRES_POOL_CHECKED_IN,
    POSTGRES_POOL_CHECKED_OUT,
    POSTGRES_POOL_OVERFLOW,
    POSTGRES_POOL_SIZE,
    REDIS_AVAILABLE,
    REDIS_BLOCKED_CLIENTS,
    REDIS_CONNECTED_CLIENTS,
    REDIS_EVICTED_KEYS_TOTAL,
    REDIS_KEYS,
    REDIS_KEYSPACE_HITS_TOTAL,
    REDIS_KEYSPACE_MISSES_TOTAL,
    REDIS_USED_MEMORY_BYTES,
    RUNPOD_JOBS,
)


logger = logging.getLogger(
    "app.observability.collectors"
)


class OperationalMetricsService:
    WAITING_STATUSES = (
        "pending",
        "scheduled",
        "queued",
        "retrying",
    )

    ACTIVE_STATUSES = (
        "claimed",
        "running",
        "cancel_requested",
    )

    def _record_error(
        self,
        *,
        collector: str,
        error: Exception,
    ) -> None:
        OBSERVABILITY_COLLECTOR_ERRORS_TOTAL.labels(
            collector=collector,
            error_type=error.__class__.__name__,
        ).inc()

        logger.warning(
            "Operational metric collector failed.",
            extra={
                "collector": collector,
                "error_type": (
                    error.__class__.__name__
                ),
                "error_message": str(error),
            },
        )

    def collect_postgres(
        self,
    ) -> None:
        started_at = time.perf_counter()

        try:
            with engine.connect() as connection:
                connection.execute(
                    text("SELECT 1")
                )

            POSTGRES_AVAILABLE.set(1)

        except SQLAlchemyError as error:
            POSTGRES_AVAILABLE.set(0)

            self._record_error(
                collector="postgres",
                error=error,
            )

        finally:
            POSTGRES_HEALTH_CHECK_DURATION_SECONDS.observe(
                time.perf_counter()
                - started_at
            )

        pool = engine.pool

        try:
            size_method = getattr(
                pool,
                "size",
                None,
            )

            checked_out_method = getattr(
                pool,
                "checkedout",
                None,
            )

            checked_in_method = getattr(
                pool,
                "checkedin",
                None,
            )

            overflow_method = getattr(
                pool,
                "overflow",
                None,
            )

            if callable(size_method):
                POSTGRES_POOL_SIZE.set(
                    float(size_method())
                )

            if callable(checked_out_method):
                POSTGRES_POOL_CHECKED_OUT.set(
                    float(
                        checked_out_method()
                    )
                )

            if callable(checked_in_method):
                POSTGRES_POOL_CHECKED_IN.set(
                    float(
                        checked_in_method()
                    )
                )

            if callable(overflow_method):
                POSTGRES_POOL_OVERFLOW.set(
                    float(
                        overflow_method()
                    )
                )

        except Exception as error:
            self._record_error(
                collector="postgres_pool",
                error=error,
            )

    def collect_redis(
        self,
    ) -> None:
        try:
            client = redis_client.get_client()

            if not client.ping():
                REDIS_AVAILABLE.set(0)
                return

            REDIS_AVAILABLE.set(1)

            memory_info = client.info(
                section="memory"
            )

            clients_info = client.info(
                section="clients"
            )

            stats_info = client.info(
                section="stats"
            )

            keyspace_info = client.info(
                section="keyspace"
            )

            REDIS_USED_MEMORY_BYTES.set(
                int(
                    memory_info.get(
                        "used_memory",
                        0,
                    )
                )
            )

            REDIS_CONNECTED_CLIENTS.set(
                int(
                    clients_info.get(
                        "connected_clients",
                        0,
                    )
                )
            )

            REDIS_BLOCKED_CLIENTS.set(
                int(
                    clients_info.get(
                        "blocked_clients",
                        0,
                    )
                )
            )

            REDIS_KEYSPACE_HITS_TOTAL.set(
                int(
                    stats_info.get(
                        "keyspace_hits",
                        0,
                    )
                )
            )

            REDIS_KEYSPACE_MISSES_TOTAL.set(
                int(
                    stats_info.get(
                        "keyspace_misses",
                        0,
                    )
                )
            )

            REDIS_EVICTED_KEYS_TOTAL.set(
                int(
                    stats_info.get(
                        "evicted_keys",
                        0,
                    )
                )
            )

            REDIS_KEYS.clear()

            for database, values in (
                keyspace_info.items()
            ):
                if not isinstance(
                    values,
                    dict,
                ):
                    continue

                REDIS_KEYS.labels(
                    database=str(database)
                ).set(
                    int(
                        values.get(
                            "keys",
                            0,
                        )
                    )
                )

        except RedisError as error:
            REDIS_AVAILABLE.set(0)

            self._record_error(
                collector="redis",
                error=error,
            )

    def collect_background_jobs(
        self,
        db: Session,
    ) -> None:
        try:
            rows = db.execute(
                text(
                    """
                    SELECT
                        queue_name,
                        status,
                        execution_mode,
                        COUNT(*) AS total
                    FROM background_jobs
                    GROUP BY
                        queue_name,
                        status,
                        execution_mode
                    """
                )
            ).mappings().all()

            BACKGROUND_JOBS.clear()

            for row in rows:
                BACKGROUND_JOBS.labels(
                    queue_name=str(
                        row["queue_name"]
                    ),
                    status=str(
                        row["status"]
                    ),
                    execution_mode=str(
                        row["execution_mode"]
                    ),
                ).set(
                    int(row["total"])
                )

            expired_leases = db.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM background_jobs
                    WHERE status IN (
                        'claimed',
                        'running',
                        'cancel_requested'
                    )
                    AND lease_expires_at IS NOT NULL
                    AND lease_expires_at <= NOW()
                    """
                )
            ).scalar_one()

            BACKGROUND_JOB_EXPIRED_LEASES.set(
                int(expired_leases)
            )

            queue_rows = db.execute(
                text(
                    """
                    SELECT
                        queue_name,
                        EXTRACT(
                            EPOCH FROM (
                                NOW() - MIN(created_at)
                            )
                        ) AS oldest_age_seconds
                    FROM background_jobs
                    WHERE status IN (
                        'pending',
                        'scheduled',
                        'queued',
                        'retrying'
                    )
                    GROUP BY queue_name
                    """
                )
            ).mappings().all()

            BACKGROUND_JOB_QUEUE_OLDEST_AGE_SECONDS.clear()

            for row in queue_rows:
                BACKGROUND_JOB_QUEUE_OLDEST_AGE_SECONDS.labels(
                    queue_name=str(
                        row["queue_name"]
                    )
                ).set(
                    max(
                        float(
                            row[
                                "oldest_age_seconds"
                            ]
                            or 0
                        ),
                        0.0,
                    )
                )

            runpod_rows = db.execute(
                text(
                    """
                    SELECT
                        COALESCE(
                            provider_endpoint_id,
                            'unconfigured'
                        ) AS endpoint_id,
                        status,
                        COUNT(*) AS total
                    FROM background_jobs
                    WHERE execution_mode =
                        'runpod_serverless'
                    GROUP BY
                        provider_endpoint_id,
                        status
                    """
                )
            ).mappings().all()

            RUNPOD_JOBS.clear()

            for row in runpod_rows:
                RUNPOD_JOBS.labels(
                    endpoint_id=str(
                        row["endpoint_id"]
                    ),
                    status=str(
                        row["status"]
                    ),
                ).set(
                    int(row["total"])
                )

        except (
            SQLAlchemyError,
            KeyError,
            TypeError,
            ValueError,
        ) as error:
            self._record_error(
                collector="background_jobs",
                error=error,
            )

    def collect_all(
        self,
        db: Session,
    ) -> dict[str, Any]:
        started_at = time.perf_counter()

        self.collect_postgres()
        self.collect_redis()
        self.collect_background_jobs(db)

        return {
            "collected": True,
            "duration_ms": round(
                (
                    time.perf_counter()
                    - started_at
                )
                * 1000,
                3,
            ),
            "collected_at": datetime.now(
                timezone.utc
            ).isoformat(),
        }


operational_metrics_service = (
    OperationalMetricsService()
)