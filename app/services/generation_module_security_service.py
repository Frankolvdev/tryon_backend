from __future__ import annotations

from app.common.exceptions import AppException
from app.common.generation_module_enums import GenerationExecutionEngine
from app.core.config import settings


class GenerationModuleSecurityService:
    def policy(self) -> dict:
        return {
            "user_allowed_engines": [GenerationExecutionEngine.SIMULATED.value],
            "admin_allowed_engines": [item.value for item in GenerationExecutionEngine],
            "max_active_executions_per_user": settings.GENERATION_MAX_ACTIVE_EXECUTIONS_PER_USER,
            "max_history_page_size": settings.GENERATION_MAX_HISTORY_PAGE_SIZE,
            "python_steps_admin_only": True,
            "audit_enabled": True,
        }

    def ensure_user_can_start(self, runtime_service, *, user_id: int, engine: GenerationExecutionEngine) -> None:
        if engine != GenerationExecutionEngine.SIMULATED:
            raise AppException("This execution engine is not available to end users.")
        items, _ = runtime_service.list(user_id=user_id, skip=0, limit=1000)
        active = sum(1 for item in items if item.status in {"queued", "running"})
        if active >= settings.GENERATION_MAX_ACTIVE_EXECUTIONS_PER_USER:
            raise AppException("You have reached the maximum number of active generation executions.")


generation_module_security_service = GenerationModuleSecurityService()
