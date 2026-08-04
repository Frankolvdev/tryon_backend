from __future__ import annotations

from app.common.exceptions import AppException

TERMINAL_EXECUTION_STATES = frozenset({"completed", "failed", "cancelled"})
ACTIVE_EXECUTION_STATES = frozenset({"queued", "running"})

_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "queued": frozenset({"queued", "running", "cancelled", "failed"}),
    "running": frozenset({"running", "completed", "cancelled", "failed"}),
    "completed": frozenset({"completed"}),
    "cancelled": frozenset({"cancelled"}),
    "failed": frozenset({"failed"}),
}


def validate_execution_transition(current: str, target: str) -> None:
    current_value = str(current or "").lower()
    target_value = str(target or "").lower()
    allowed = _ALLOWED_TRANSITIONS.get(current_value)
    if allowed is None or target_value not in allowed:
        raise AppException(
            f"Invalid generation execution transition: {current_value!r} -> {target_value!r}."
        )


def transition_execution(execution, target: str) -> None:
    validate_execution_transition(execution.status, target)
    execution.status = target
