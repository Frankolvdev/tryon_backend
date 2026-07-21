from sqlalchemy.orm import Session

from app.common.enums import IntegrationProvider
from app.services.comfyui_local_adapter_service import comfyui_local_adapter_service
from app.services.integration_service import integration_service
from app.services.runpod_config_service import runpod_config_service
from app.services.runpod_serverless_adapter_service import runpod_serverless_adapter_service
from app.services.runtime_settings_service import runtime_settings_service
from app.repositories.system_setting_repository import system_setting_repository
from app.schemas.system_setting import SystemSettingUpdate
from app.services.system_setting_service import system_setting_service


class AiProviderOrchestrationService:
    VALID_MODES = {
        "simulated",
        "comfyui_local",
        "runpod_serverless",
        "auto",
    }

    def _comfyui_enabled(self, db: Session) -> bool:
        try:
            return bool(
                integration_service.get_config(
                    db,
                    IntegrationProvider.COMFYUI,
                ).is_enabled
            )
        except Exception:
            return False

    def _simulated_health(self, db: Session) -> dict:
        enabled = runtime_settings_service.get_bool(
            db,
            "simulated_engine_enabled",
            default=True,
        )
        return {
            "provider": "simulated",
            "enabled": enabled,
            "configured": True,
            "available": enabled,
            "message": (
                "Motor simulado disponible."
                if enabled
                else "Motor simulado desactivado."
            ),
            "details": {
                "delay_seconds": runtime_settings_service.get_float(
                    db,
                    "simulated_engine_delay_seconds",
                    default=2.0,
                ),
                "failure_rate": runtime_settings_service.get_float(
                    db,
                    "simulated_engine_failure_rate",
                    default=0.0,
                ),
            },
        }

    def _comfyui_health(self, db: Session) -> dict:
        enabled = self._comfyui_enabled(db)
        health = comfyui_local_adapter_service.health()
        return {
            "provider": "comfyui_local",
            "enabled": enabled,
            "configured": bool(health.get("base_url")),
            "available": enabled and bool(health.get("available")),
            "message": (
                "ComfyUI disponible."
                if enabled and health.get("available")
                else health.get("error") or "ComfyUI no disponible."
            ),
            "details": health,
        }

    def _runpod_health(self, db: Session) -> dict:
        enabled = runtime_settings_service.runpod_enabled(db)
        config = runpod_config_service.get_active_config(db)
        configured = bool(config and config.endpoint_id)
        health: dict = {}

        if configured:
            health = runpod_serverless_adapter_service.health(
                db,
                endpoint_id=config.endpoint_id,
            )

        return {
            "provider": "runpod_serverless",
            "enabled": enabled,
            "configured": configured,
            "available": enabled and configured and bool(health.get("available")),
            "message": (
                "RunPod disponible."
                if enabled and configured and health.get("available")
                else health.get("error")
                or "RunPod no está habilitado o configurado."
            ),
            "details": {
                "config_id": config.id if config else None,
                "endpoint_id": config.endpoint_id if config else None,
                **health,
            },
        }

    def overview(self, db: Session) -> dict:
        mode = runtime_settings_service.get_string(
            db,
            "ai_execution_mode",
            default="simulated",
        ).lower()
        if mode not in self.VALID_MODES:
            mode = "simulated"

        providers = [
            self._simulated_health(db),
            self._comfyui_health(db),
            self._runpod_health(db),
        ]

        fallback_order = [
            "runpod_serverless",
            "comfyui_local",
            "simulated",
        ]

        if mode == "auto":
            selected_provider = next(
                (
                    provider["provider"]
                    for provider in providers
                    if provider["provider"] in fallback_order
                    and provider["available"]
                ),
                "simulated",
            )
        else:
            selected_provider = mode

        return {
            "execution_mode": mode,
            "selected_provider": selected_provider,
            "fallback_order": fallback_order,
            "providers": providers,
        }

    def set_execution_mode(self, db: Session, *, execution_mode: str) -> dict:
        if execution_mode not in self.VALID_MODES:
            raise ValueError("Invalid AI execution mode.")

        setting = system_setting_repository.get_by_key(db, "ai_execution_mode")
        if setting is None:
            raise ValueError("AI execution mode setting is not initialized.")

        system_setting_service.update_setting(
            db,
            setting.id,
            SystemSettingUpdate(value=execution_mode),
        )
        return self.overview(db)


ai_provider_orchestration_service = AiProviderOrchestrationService()
