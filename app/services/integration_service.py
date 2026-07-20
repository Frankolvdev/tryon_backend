import json
from typing import Any

from sqlalchemy.orm import Session

from app.common.enums import (
    IntegrationHealthStatus,
    IntegrationProvider,
    IntegrationStatus,
)
from app.common.exceptions import ConflictException, NotFoundException
from app.common.time import utc_now
from app.models.integration_config import IntegrationConfig
from app.models.integration_event import IntegrationEvent
from app.repositories.integration_config_repository import integration_config_repository
from app.repositories.integration_event_repository import integration_event_repository
from app.schemas.integration import (
    IntegrationConfigCreate,
    IntegrationConfigResponse,
    IntegrationConfigUpdate,
    IntegrationEventResponse,
    IntegrationHealthResponse,
)


class IntegrationService:
    def _serialize_json(self, value: Any) -> str:
        return json.dumps(value or {}, ensure_ascii=False, default=str)

    def _parse_json(self, value: str | None) -> dict[str, Any]:
        if not value:
            return {}

        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}

    def _to_config_response(self, config: IntegrationConfig) -> IntegrationConfigResponse:
        return IntegrationConfigResponse(
            id=config.id,
            provider=config.provider,
            name=config.name,
            status=config.status,
            is_enabled=config.is_enabled,
            base_url=config.base_url,
            api_key_configured=bool(config.api_key),
            api_secret_configured=bool(config.api_secret),
            webhook_secret_configured=bool(config.webhook_secret),
            config=self._parse_json(config.config_json),
            last_health_status=config.last_health_status,
            last_health_message=config.last_health_message,
            last_checked_at=config.last_checked_at,
            created_at=config.created_at,
            updated_at=config.updated_at,
        )

    def _to_event_response(self, event: IntegrationEvent) -> IntegrationEventResponse:
        return IntegrationEventResponse(
            id=event.id,
            provider=event.provider,
            event_type=event.event_type,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            payload=self._parse_json(event.payload_json),
            response=self._parse_json(event.response_json),
            error_message=event.error_message,
            created_at=event.created_at,
        )

    def list_configs(self, db: Session) -> list[IntegrationConfigResponse]:
        configs = integration_config_repository.list_all(db)
        return [self._to_config_response(config) for config in configs]

    def get_config(self, db: Session, provider: IntegrationProvider) -> IntegrationConfig:
        config = integration_config_repository.get_by_provider(db, provider.value)

        if not config:
            raise NotFoundException("Integration config not found.")

        return config

    def get_config_response(
        self,
        db: Session,
        provider: IntegrationProvider,
    ) -> IntegrationConfigResponse:
        return self._to_config_response(self.get_config(db, provider))

    def create_config(
        self,
        db: Session,
        data: IntegrationConfigCreate,
    ) -> IntegrationConfigResponse:
        existing = integration_config_repository.get_by_provider(db, data.provider.value)

        if existing:
            raise ConflictException("Integration provider already exists.")

        config = integration_config_repository.create(
            db,
            data={
                "provider": data.provider.value,
                "name": data.name,
                "status": data.status.value,
                "is_enabled": data.is_enabled,
                "base_url": data.base_url,
                "api_key": data.api_key,
                "api_secret": data.api_secret,
                "webhook_secret": data.webhook_secret,
                "config_json": self._serialize_json(data.config),
            },
        )

        return self._to_config_response(config)

    def update_config(
        self,
        db: Session,
        provider: IntegrationProvider,
        data: IntegrationConfigUpdate,
    ) -> IntegrationConfigResponse:
        config = self.get_config(db, provider)
        update_data = data.model_dump(exclude_unset=True)
        final_data = {}

        for field in [
            "name",
            "is_enabled",
            "base_url",
            "api_key",
            "api_secret",
            "webhook_secret",
        ]:
            if field in update_data:
                final_data[field] = update_data[field]

        if "status" in update_data and update_data["status"] is not None:
            final_data["status"] = update_data["status"].value

        if "config" in update_data and update_data["config"] is not None:
            final_data["config_json"] = self._serialize_json(update_data["config"])

        updated = integration_config_repository.update(
            db,
            db_obj=config,
            data=final_data,
        )

        return self._to_config_response(updated)

    def record_event(
        self,
        db: Session,
        *,
        provider: IntegrationProvider | str,
        event_type: str,
        entity_type: str | None = None,
        entity_id: str | None = None,
        payload: dict[str, Any] | None = None,
        response: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> IntegrationEvent:
        provider_value = provider.value if hasattr(provider, "value") else str(provider)

        return integration_event_repository.create(
            db,
            data={
                "provider": provider_value,
                "event_type": event_type,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "payload_json": self._serialize_json(payload),
                "response_json": self._serialize_json(response),
                "error_message": error_message,
            },
        )

    def list_events(
        self,
        db: Session,
        *,
        provider: IntegrationProvider | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[IntegrationEventResponse]:
        if provider:
            events = integration_event_repository.list_by_provider(
                db,
                provider.value,
                skip=skip,
                limit=limit,
            )
        else:
            events = integration_event_repository.list_all(
                db,
                skip=skip,
                limit=limit,
            )

        return [self._to_event_response(event) for event in events]

    def update_health(
        self,
        db: Session,
        *,
        provider: IntegrationProvider,
        health: IntegrationHealthResponse,
    ) -> IntegrationHealthResponse:
        config = self.get_config(db, provider)

        config.last_health_status = health.status.value
        config.last_health_message = health.message
        config.last_checked_at = utc_now()

        if health.status == IntegrationHealthStatus.HEALTHY:
            config.status = (
                IntegrationStatus.ENABLED.value
                if config.is_enabled
                else IntegrationStatus.DISABLED.value
            )
        elif health.status in [IntegrationHealthStatus.DEGRADED, IntegrationHealthStatus.DOWN]:
            config.status = IntegrationStatus.ERROR.value

        db.add(config)
        db.commit()

        return health

    def health_check(
        self,
        db: Session,
        provider: IntegrationProvider,
    ) -> IntegrationHealthResponse:
        config = self.get_config(db, provider)

        if not config.is_enabled:
            health = IntegrationHealthResponse(
                provider=provider,
                status=IntegrationHealthStatus.UNKNOWN,
                message="Integration is disabled.",
                metadata={},
            )
            return self.update_health(db, provider=provider, health=health)

        try:
            if provider == IntegrationProvider.RUNPOD:
                from app.services.runpod_client_service import runpod_client_service

                result = runpod_client_service.health_check(db)
                return self.update_health(
                    db,
                    provider=provider,
                    health=IntegrationHealthResponse(
                        provider=provider,
                        status=IntegrationHealthStatus.HEALTHY,
                        message="RunPod API is reachable.",
                        metadata=result,
                    ),
                )

            if provider == IntegrationProvider.COMFYUI:
                from app.services.comfyui_client_service import comfyui_client_service

                result = comfyui_client_service.health_check(db)
                return self.update_health(
                    db,
                    provider=provider,
                    health=IntegrationHealthResponse(
                        provider=provider,
                        status=IntegrationHealthStatus.HEALTHY,
                        message="ComfyUI API is reachable.",
                        metadata=result,
                    ),
                )

            if provider == IntegrationProvider.S3:
                from app.services.s3_storage_service import s3_storage_service

                result = s3_storage_service.health_check(db)
                return self.update_health(
                    db,
                    provider=provider,
                    health=IntegrationHealthResponse(
                        provider=provider,
                        status=IntegrationHealthStatus.HEALTHY,
                        message="S3 storage is reachable.",
                        metadata=result,
                    ),
                )

            if provider == IntegrationProvider.SMTP:
                from app.services.smtp_email_service import smtp_email_service

                result = smtp_email_service.health_check(db)
                return self.update_health(
                    db,
                    provider=provider,
                    health=IntegrationHealthResponse(
                        provider=provider,
                        status=IntegrationHealthStatus.HEALTHY,
                        message="SMTP server is reachable.",
                        metadata=result,
                    ),
                )

            health = IntegrationHealthResponse(
                provider=provider,
                status=IntegrationHealthStatus.HEALTHY,
                message="Base integration config is enabled.",
                metadata={
                    "base_url_configured": bool(config.base_url),
                    "api_key_configured": bool(config.api_key),
                    "api_secret_configured": bool(config.api_secret),
                    "webhook_secret_configured": bool(config.webhook_secret),
                },
            )

            return self.update_health(db, provider=provider, health=health)

        except Exception as error:
            return self.update_health(
                db,
                provider=provider,
                health=IntegrationHealthResponse(
                    provider=provider,
                    status=IntegrationHealthStatus.DOWN,
                    message=str(error),
                    metadata={},
                ),
            )

    def seed_defaults(self, db: Session) -> dict:
        defaults = [
            IntegrationConfigCreate(
                provider=IntegrationProvider.STRIPE,
                name="Stripe",
                status=IntegrationStatus.DISABLED,
                is_enabled=False,
                base_url="https://api.stripe.com",
                config={"mode": "test", "currency": "usd"},
            ),
            IntegrationConfigCreate(
                provider=IntegrationProvider.RUNPOD,
                name="RunPod",
                status=IntegrationStatus.DISABLED,
                is_enabled=False,
                base_url="https://api.runpod.ai",
                config={"mode": "serverless", "default_timeout_seconds": 900},
            ),
            IntegrationConfigCreate(
                provider=IntegrationProvider.COMFYUI,
                name="ComfyUI",
                status=IntegrationStatus.DISABLED,
                is_enabled=False,
                base_url="http://127.0.0.1:8188",
                config={
                    "mode": "local",
                    "workflows_dir": "workflows",
                    "poll_timeout_seconds": 300,
                    "poll_interval_seconds": 2,
                    "person_image_node_id": "person_image",
                    "item_image_node_id": "item_image",
                    "prompt_node_id": None,
                    "person_image_path": ["inputs", "image"],
                    "item_image_path": ["inputs", "image"],
                    "prompt_path": ["inputs", "text"],
                },
            ),
            IntegrationConfigCreate(
                provider=IntegrationProvider.S3,
                name="S3 Compatible Storage",
                status=IntegrationStatus.DISABLED,
                is_enabled=False,
                base_url=None,
                config={
                    "bucket": "",
                    "region": "",
                    "endpoint_url": "",
                    "cdn_base_url": "",
                },
            ),
            IntegrationConfigCreate(
                provider=IntegrationProvider.SMTP,
                name="SMTP Email",
                status=IntegrationStatus.DISABLED,
                is_enabled=False,
                config={
                    "host": "",
                    "port": 587,
                    "use_tls": True,
                    "from_email": "",
                    "from_name": "AI Try-On Platform",
                },
            ),
            IntegrationConfigCreate(
                provider=IntegrationProvider.GOOGLE_OAUTH,
                name="Google OAuth",
                status=IntegrationStatus.DISABLED,
                is_enabled=False,
                config={"redirect_uri": ""},
            ),
            IntegrationConfigCreate(
                provider=IntegrationProvider.GITHUB_OAUTH,
                name="GitHub OAuth",
                status=IntegrationStatus.DISABLED,
                is_enabled=False,
                config={"redirect_uri": ""},
            ),
            IntegrationConfigCreate(
                provider=IntegrationProvider.APPLE_OAUTH,
                name="Apple OAuth",
                status=IntegrationStatus.DISABLED,
                is_enabled=False,
                config={"redirect_uri": ""},
            ),
            IntegrationConfigCreate(
                provider=IntegrationProvider.FACEBOOK_OAUTH,
                name="Facebook OAuth",
                status=IntegrationStatus.DISABLED,
                is_enabled=False,
                config={"redirect_uri": ""},
            ),
        ]

        created = 0
        skipped = 0

        for item in defaults:
            existing = integration_config_repository.get_by_provider(db, item.provider.value)

            if existing:
                skipped += 1
                continue

            self.create_config(db, item)
            created += 1

        return {"created": created, "skipped": skipped, "total": len(defaults)}


integration_service = IntegrationService()