import logging
import threading
import time

from app.db.database import SessionLocal
from app.services.application_health_service import (
    application_health_service,
)
from app.services.operational_metrics_service import (
    operational_metrics_service,
)


logger = logging.getLogger(
    "app.observability.metrics_collection"
)


class MetricsCollectionService:
    def __init__(self):
        self._thread: (
            threading.Thread | None
        ) = None

        self._stop_event = (
            threading.Event()
        )

        self._interval_seconds = 30

    def _collect_once(
        self,
    ) -> None:
        db = SessionLocal()

        try:
            operational_metrics_service.collect_all(
                db
            )

            application_health_service.readiness(
                db
            )

        except Exception:
            logger.exception(
                "Periodic metric collection failed."
            )

        finally:
            db.close()

    def _run(
        self,
    ) -> None:
        while not self._stop_event.is_set():
            self._collect_once()

            self._stop_event.wait(
                self._interval_seconds
            )

    def start(
        self,
        *,
        interval_seconds: int = 30,
    ) -> None:
        if (
            self._thread
            and self._thread.is_alive()
        ):
            return

        self._interval_seconds = max(
            int(interval_seconds),
            5,
        )

        self._stop_event.clear()

        self._thread = threading.Thread(
            target=self._run,
            name=(
                "operational-metrics-collector"
            ),
            daemon=True,
        )

        self._thread.start()

        logger.info(
            "Metrics collection service started.",
            extra={
                "interval_seconds": (
                    self._interval_seconds
                ),
            },
        )

    def stop(
        self,
    ) -> None:
        self._stop_event.set()

        if self._thread:
            self._thread.join(
                timeout=5
            )

        self._thread = None

        logger.info(
            "Metrics collection service stopped."
        )


metrics_collection_service = (
    MetricsCollectionService()
)