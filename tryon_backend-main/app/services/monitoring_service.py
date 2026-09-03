from pathlib import Path

import psutil
import redis
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.schemas.monitoring import (
    MonitoringResponse,
    ServiceHealthResponse,
    SystemResourcesResponse,
)
from app.services.runtime_settings_service import runtime_settings_service


class MonitoringService:
    def check_api(self) -> ServiceHealthResponse:
        return ServiceHealthResponse(
            service="api",
            status="ok",
            details={
                "app_name": settings.APP_NAME,
                "app_env": settings.APP_ENV,
                "app_version": settings.APP_VERSION,
            },
        )

    def check_database(self, db: Session) -> ServiceHealthResponse:
        try:
            db.execute(text("SELECT 1"))
            return ServiceHealthResponse(
                service="postgresql",
                status="ok",
            )
        except Exception as error:
            return ServiceHealthResponse(
                service="postgresql",
                status="error",
                details={"error": str(error)},
            )

    def check_redis(self) -> ServiceHealthResponse:
        try:
            client = redis.Redis.from_url(
                settings.REDIS_URL,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            client.ping()

            return ServiceHealthResponse(
                service="redis",
                status="ok",
            )
        except Exception as error:
            return ServiceHealthResponse(
                service="redis",
                status="error",
                details={"error": str(error)},
            )

    def check_storage(self, db: Session) -> ServiceHealthResponse:
        try:
            storage_dir = runtime_settings_service.local_storage_dir(db)
            storage_provider = runtime_settings_service.storage_provider(db)

            storage_path = Path(storage_dir)
            storage_path.mkdir(parents=True, exist_ok=True)

            test_file = storage_path / ".healthcheck"
            test_file.write_text("ok", encoding="utf-8")
            test_file.unlink(missing_ok=True)

            return ServiceHealthResponse(
                service="storage",
                status="ok",
                details={
                    "provider": storage_provider,
                    "local_storage_dir": storage_dir,
                },
            )
        except Exception as error:
            return ServiceHealthResponse(
                service="storage",
                status="error",
                details={"error": str(error)},
            )

    def get_resources(self) -> SystemResourcesResponse:
        disk = psutil.disk_usage(".")

        return SystemResourcesResponse(
            cpu_percent=psutil.cpu_percent(interval=0.1),
            memory_percent=psutil.virtual_memory().percent,
            disk_percent=disk.percent,
        )

    def get_monitoring_status(self, db: Session) -> MonitoringResponse:
        return MonitoringResponse(
            api=self.check_api(),
            database=self.check_database(db),
            redis=self.check_redis(),
            storage=self.check_storage(db),
            resources=self.get_resources(),
        )


monitoring_service = MonitoringService()