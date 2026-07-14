import json
from typing import Any

from sqlalchemy.orm import Session

from app.common.enums import IntegrationProvider
from app.core.config import settings
from app.services.integration_service import integration_service


class RunPodRuntimeConfigService:
    def _read_metadata(
        self,
        config: Any,
    ) -> dict[str, Any]:
        possible_values = [
            getattr(config, "metadata", None),
            getattr(config, "metadata_json", None),
            getattr(config, "settings_json", None),
            getattr(config, "configuration_json", None),
        ]

        for value in possible_values:
            if isinstance(value, dict):
                return value

            if isinstance(value, str) and value:
                try:
                    parsed = json.loads(value)

                    if isinstance(parsed, dict):
                        return parsed
                except json.JSONDecodeError:
                    continue

        return {}

    def _config_value(
        self,
        config: Any,
        metadata: dict[str, Any],
        names: list[str],
    ) -> str | None:
        for name in names:
            value = getattr(
                config,
                name,
                None,
            )

            if value:
                return str(value)

            metadata_value = metadata.get(name)

            if metadata_value:
                return str(metadata_value)

        return None

    def _database_config(
        self,
        db: Session,
    ) -> Any | None:
        try:
            return integration_service.get_config(
                db,
                IntegrationProvider.RUNPOD,
            )
        except Exception:
            return None

    def api_key(
        self,
        db: Session,
    ) -> str | None:
        config = self._database_config(db)

        if config is not None:
            metadata = self._read_metadata(config)

            value = self._config_value(
                config,
                metadata,
                [
                    "api_key",
                    "secret_key",
                    "token",
                    "runpod_api_key",
                ],
            )

            if value:
                return value

        value = getattr(
            settings,
            "RUNPOD_API_KEY",
            None,
        )

        return str(value) if value else None

    def endpoint_id(
        self,
        db: Session,
    ) -> str | None:
        config = self._database_config(db)

        if config is not None:
            metadata = self._read_metadata(config)

            value = self._config_value(
                config,
                metadata,
                [
                    "endpoint_id",
                    "runpod_endpoint_id",
                    "provider_endpoint_id",
                ],
            )

            if value:
                return value

        value = getattr(
            settings,
            "RUNPOD_ENDPOINT_ID",
            None,
        )

        return str(value) if value else None

    def base_url(
        self,
        db: Session,
    ) -> str:
        config = self._database_config(db)

        if config is not None:
            metadata = self._read_metadata(config)

            value = self._config_value(
                config,
                metadata,
                [
                    "base_url",
                    "api_base_url",
                    "runpod_base_url",
                ],
            )

            if value:
                return value.rstrip("/")

        configured = getattr(
            settings,
            "RUNPOD_BASE_URL",
            None,
        )

        if configured:
            return str(configured).rstrip("/")

        return "https://api.runpod.ai/v2"

    def callback_secret(
        self,
        db: Session | None = None,
    ) -> str | None:
        if db is not None:
            config = self._database_config(db)

            if config is not None:
                metadata = self._read_metadata(
                    config
                )

                value = self._config_value(
                    config,
                    metadata,
                    [
                        "callback_secret",
                        "webhook_secret",
                        "runpod_callback_secret",
                    ],
                )

                if value:
                    return value

        value = getattr(
            settings,
            "RUNPOD_CALLBACK_SECRET",
            None,
        )

        return str(value) if value else None

    def callback_url(
        self,
        db: Session,
    ) -> str | None:
        config = self._database_config(db)

        if config is not None:
            metadata = self._read_metadata(config)

            value = self._config_value(
                config,
                metadata,
                [
                    "callback_url",
                    "webhook_url",
                    "runpod_callback_url",
                ],
            )

            if value:
                return value

        value = getattr(
            settings,
            "RUNPOD_CALLBACK_URL",
            None,
        )

        return str(value) if value else None

    def http_timeout_seconds(self) -> float:
        return float(
            getattr(
                settings,
                "RUNPOD_HTTP_TIMEOUT_SECONDS",
                60,
            )
        )

    def polling_interval_seconds(self) -> float:
        return float(
            getattr(
                settings,
                "RUNPOD_POLL_INTERVAL_SECONDS",
                2,
            )
        )


runpod_runtime_config_service = (
    RunPodRuntimeConfigService()
)