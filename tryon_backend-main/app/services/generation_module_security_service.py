from __future__ import annotations

from app.common.exceptions import AppException
from app.common.generation_module_enums import GenerationExecutionEngine
from app.core.config import settings
from app.common.enums import UserRole


class GenerationModuleSecurityService:
    @staticmethod
    def _user_allowed_engines() -> list[GenerationExecutionEngine]:
        configured = [item.strip() for item in settings.GENERATION_USER_ALLOWED_ENGINES.split(",") if item.strip()]
        allowed: list[GenerationExecutionEngine] = []
        for value in configured:
            try:
                engine = GenerationExecutionEngine(value)
            except ValueError:
                continue
            if engine not in allowed:
                allowed.append(engine)
        return allowed or [GenerationExecutionEngine.SIMULATED]

    def policy(self) -> dict:
        return {
            "user_allowed_engines": [item.value for item in self._user_allowed_engines()],
            "admin_allowed_engines": [item.value for item in GenerationExecutionEngine],
            "max_active_executions_per_user": settings.GENERATION_MAX_ACTIVE_EXECUTIONS_PER_USER,
            "max_history_page_size": settings.GENERATION_MAX_HISTORY_PAGE_SIZE,
            "python_steps_admin_only": True,
            "audit_enabled": True,
        }

    def ensure_user_can_start(
        self,
        runtime_service,
        *,
        user_id: int,
        engine: GenerationExecutionEngine,
        user_role: str = UserRole.USER.value,
    ) -> None:
        if user_role == UserRole.OWNER.value:
            if engine != GenerationExecutionEngine.OWNER_LOCAL:
                raise AppException("Owner accounts may only use Owner Local.")
        else:
            if engine == GenerationExecutionEngine.OWNER_LOCAL:
                raise AppException("Owner Local is reserved for the owner account.")
            if engine not in self._user_allowed_engines():
                raise AppException("This execution engine is not available to end users.")
        items, _ = runtime_service.list(user_id=user_id, skip=0, limit=1000)
        active = sum(1 for item in items if item.status in {"queued", "running"})
        if active >= settings.GENERATION_MAX_ACTIVE_EXECUTIONS_PER_USER:
            raise AppException("You have reached the maximum number of active generation executions.")


generation_module_security_service = GenerationModuleSecurityService()
