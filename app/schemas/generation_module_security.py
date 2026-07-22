from pydantic import BaseModel, Field


class GenerationRuntimeSecurityPolicyResponse(BaseModel):
    user_allowed_engines: list[str]
    admin_allowed_engines: list[str]
    max_active_executions_per_user: int
    max_history_page_size: int
    python_steps_admin_only: bool = True
    audit_enabled: bool = True


class GenerationRuntimeSecuritySummary(BaseModel):
    policy: GenerationRuntimeSecurityPolicyResponse
    active_executions: int
    active_user_executions: int
    tracked_executions: int
