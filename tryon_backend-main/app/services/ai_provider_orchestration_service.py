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
from app.services.infrastructure_provider_service import InfrastructureProviderService
from app.services.ai_engine_settings_service import ai_engine_settings_service


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
        # Runtime Builder can create or discover the Endpoint and Template during
        # deployment. Their IDs are therefore outputs of provisioning, not
        # prerequisites for showing RunPod as configured in Motor IA.
        infra = InfrastructureProviderService.get_runpod(db)
        configured = bool(
            infra.api_key
            and infra.endpoint_name
            and infra.template_name
            and infra.gpu_type_ids
        )
        available = bool(infra.enabled and configured)

        return {
            "provider": "runpod_serverless",
            "enabled": bool(infra.enabled),
            "configured": configured,
            "available": available,
            "message": (
                "RunPod disponible para desplegar o utilizar el runtime."
                if available
                else "Completa y activa la configuración mínima de RunPod."
            ),
            "details": {
                "endpoint_id": infra.endpoint_id or None,
                "endpoint_name": infra.endpoint_name,
                "endpoint_will_be_created": not bool(infra.endpoint_id),
                "template_id": infra.template_id or None,
                "template_name": infra.template_name,
                "template_will_be_created": not bool(infra.template_id),
                "registry_auth_required": bool(infra.registry_auth_id),
                "network_volume_id": infra.network_volume_id or None,
                "gpu_type_ids": infra.gpu_type_ids,
            },
        }


    def _modal_health(self, db: Session) -> dict:
        config = InfrastructureProviderService.get_modal(db)
        engine = ai_engine_settings_service.get(db)
        provider_ready = bool(config.enabled and config.token_id and config.token_secret and config.app_name and config.volume_name)
        engine_ready = bool(engine.modal_gpu and engine.modal_max_containers >= engine.modal_min_containers and engine.modal_concurrency >= 1 and engine.modal_input_concurrency >= 1)
        available = provider_ready and engine_ready
        return {
            "provider": "modal", "enabled": bool(config.enabled), "configured": provider_ready, "available": available,
            "message": "Modal listo para despliegues." if available else "Completa Configuración Modal y Configuración del proveedor.",
            "details": {"app_name": config.app_name, "volume_name": config.volume_name, "gpu": engine.modal_gpu},
        }

    def _beam_health(self, db: Session) -> dict:
        config = InfrastructureProviderService.get_beam(db)
        configured = bool(
            config.api_key
            and config.deployment_name
            and config.volume_name
            and config.gpu
        )
        available = bool(config.enabled and configured)
        return {
            "provider": "beam",
            "enabled": bool(config.enabled),
            "configured": configured,
            "available": available,
            "message": (
                "Beam disponible para los módulos."
                if available
                else "Completa y activa la configuración de Beam."
            ),
            "details": {
                "deployment_name": config.deployment_name,
                "volume_name": config.volume_name,
                "gpu": config.gpu,
                "endpoint": config.endpoint,
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
            self._modal_health(db),
            self._beam_health(db),
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
