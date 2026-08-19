from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.common.exceptions import AppException
from app.common.generation_module_enums import GenerationExecutionEngine
from app.models.generation_module import GenerationModule
from app.repositories.pricing_rule_repository import pricing_rule_repository
from app.repositories.system_setting_repository import system_setting_repository
from app.services.ai_engine_settings_service import ai_engine_settings_service
from app.services.infrastructure_provider_service import infrastructure_provider_service
from app.services.provider_pricing_service import provider_pricing_service
from app.services.pricing_service import TOKEN_VALUE_KEY, pricing_service


@dataclass(frozen=True, slots=True)
class GenerationReadiness:
    provider: str
    gpu_key: str
    scaledown_seconds: int


class GenerationConfigurationReadinessService:
    """Fail closed before a generation can consume provider resources.

    This service is deliberately side-effect free: it never charges tokens,
    creates executions, dispatches jobs, or mutates provider configuration.
    """

    USER_MESSAGE = (
        "Este módulo de generación no está disponible temporalmente. "
        "Contacta con soporte. Falta configuración necesaria."
    )
    ERROR_CODE = "GENERATION_MODULE_MISSING_CONFIGURATION"

    @classmethod
    def _fail(cls, missing: list[str]) -> None:
        # Missing keys are intentionally not exposed to end users. They remain
        # available in server logs/tests through the exception object.
        exc = AppException(
            cls.USER_MESSAGE,
            status_code=409,
            error_code=cls.ERROR_CODE,
        )
        exc.missing_configuration = tuple(missing)
        raise exc

    @staticmethod
    def _positive(value: Any) -> bool:
        try:
            return Decimal(str(value)) > 0
        except Exception:
            return False

    def ensure_ready(
        self,
        db: Session,
        *,
        module_id: int,
        engine: GenerationExecutionEngine | None,
        accounting_mode: str = "commercial",
    ) -> GenerationReadiness:
        missing: list[str] = []

        module = db.get(GenerationModule, module_id)
        if module is None or not module.is_active:
            self._fail(["generation_module.active"])
        if engine is None:
            self._fail(["generation_module.default_execution_engine"])

        # Only commercial executions enter pricing/FIFO/accounting readiness.
        # Owner/admin technical executions are deliberately stopped before the
        # financial boundary and therefore must not depend on commercial token
        # configuration.
        if accounting_mode == "commercial":
            rule = pricing_rule_repository.get_for_generation_module(db, module.id)
            if rule is None:
                missing.append("pricing_rule")
            else:
                if not rule.is_active:
                    missing.append("pricing_rule.active")
                if rule.generation_module_id != module.id:
                    missing.append("pricing_rule.generation_module_id")
                if not self._positive(rule.initial_estimated_duration_seconds):
                    missing.append("pricing_rule.initial_estimated_duration_seconds")
                if int(rule.technical_margin_seconds or 0) < 0:
                    missing.append("pricing_rule.technical_margin_seconds")
                profit_per_token = Decimal(str(rule.desired_profit_per_token_usd or 0))
                token_value = Decimal(str(pricing_service.get_commercial_settings(db).token_value_usd))
                if profit_per_token < 0 or profit_per_token >= token_value:
                    missing.append("pricing_rule.desired_profit_per_token_usd")

            token_setting = system_setting_repository.get_by_key(db, TOKEN_VALUE_KEY)
            if token_setting is None or not self._positive(token_setting.value_float):
                missing.append("commercial_token_value_usd")

        provider = engine.value if hasattr(engine, "value") else str(engine)
        gpu_key = ""
        scaledown_seconds = 0

        if engine == GenerationExecutionEngine.LOCAL_DOCKER:
            cfg = infrastructure_provider_service.get_local_docker(db)
            gpu_key = str(cfg.gpu or "").strip()
            if not cfg.enabled:
                missing.append("local_docker.enabled")
            if not str(cfg.endpoint or "").strip():
                missing.append("local_docker.endpoint")
            if not gpu_key:
                missing.append("local_docker.gpu")

        elif engine == GenerationExecutionEngine.OWNER_LOCAL:
            cfg = infrastructure_provider_service.get_owner_local(db)
            gpu_key = str(cfg.gpu or "").strip()
            if not cfg.enabled:
                missing.append("owner_local.enabled")
            if not str(cfg.endpoint or "").strip():
                missing.append("owner_local.endpoint")
            if not gpu_key:
                missing.append("owner_local.gpu")

        elif engine == GenerationExecutionEngine.MODAL:
            cfg = infrastructure_provider_service.get_modal(db)
            settings = ai_engine_settings_service.get(db)
            gpu_key = str(settings.modal_gpu or cfg.gpu or "").strip()
            scaledown_seconds = int(settings.modal_scaledown_window_seconds or 0)
            if not cfg.enabled:
                missing.append("modal.enabled")
            if not str(cfg.app_name or "").strip():
                missing.append("modal.app_name")
            if not str(cfg.token_id or "").strip():
                missing.append("modal.token_id")
            if not str(cfg.token_secret or "").strip():
                missing.append("modal.token_secret")
            if not gpu_key:
                missing.append("modal.gpu")
            if scaledown_seconds < 1:
                missing.append("modal.scaledown_window_seconds")

        elif engine == GenerationExecutionEngine.RUNPOD_SERVERLESS:
            cfg = infrastructure_provider_service.get_runpod(db)
            gpu_key = str((cfg.gpu_type_ids or [""])[0]).strip()
            scaledown_seconds = int(cfg.idle_timeout_seconds or 0)
            if not cfg.enabled:
                missing.append("runpod.enabled")
            if not str(cfg.api_key or "").strip():
                missing.append("runpod.api_key")
            if not str(cfg.endpoint_id or "").strip():
                missing.append("runpod.endpoint_id")
            if not gpu_key:
                missing.append("runpod.gpu_type_ids")
            if scaledown_seconds < 1:
                missing.append("runpod.idle_timeout_seconds")

        elif engine == GenerationExecutionEngine.BEAM:
            cfg = infrastructure_provider_service.get_beam(db)
            gpu_key = str(cfg.gpu or "").strip()
            scaledown_seconds = int(cfg.keep_warm_seconds or 0)
            if not cfg.enabled:
                missing.append("beam.enabled")
            if not str(cfg.api_key or "").strip():
                missing.append("beam.api_key")
            if not str(cfg.endpoint or "").strip():
                missing.append("beam.endpoint")
            if not gpu_key:
                missing.append("beam.gpu")
            if scaledown_seconds < 0:
                missing.append("beam.keep_warm_seconds")

        else:
            # Dynamic provider billing is only well-defined for providers with
            # an explicit GPU and per-second price.
            missing.append(f"{provider}.dynamic_pricing_not_supported")

        gpu_cost = (
            provider_pricing_service.get_cost(
                db,
                provider=provider,
                gpu_key=gpu_key,
            )
            if gpu_key
            else None
        )
        if gpu_cost is None or gpu_cost <= 0:
            missing.append(f"{provider}.gpu_cost_usd_per_second")

        if missing:
            self._fail(missing)

        return GenerationReadiness(
            provider=provider,
            gpu_key=gpu_key,
            scaledown_seconds=scaledown_seconds,
        )


generation_configuration_readiness_service = GenerationConfigurationReadinessService()
