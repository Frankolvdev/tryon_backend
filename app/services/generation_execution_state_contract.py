from __future__ import annotations

from typing import Protocol


class _ExecutionLike(Protocol):
    status: str
    cancel_requested: bool


class GenerationExecutionStateContract:
    """Single execution-state policy shared by API exposure and recovery/dispatch.

    Backend supervision may keep a cancellation-pending execution attached until the
    provider confirms the terminal state. That does not make it dispatchable or an
    active generation for client UIs.
    """

    ACTIVE_STATUSES = frozenset({"queued", "running"})
    TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})

    @classmethod
    def is_terminal(cls, execution: _ExecutionLike) -> bool:
        return execution.status in cls.TERMINAL_STATUSES

    @classmethod
    def is_dispatchable(cls, execution: _ExecutionLike) -> bool:
        return execution.status == "queued" and not execution.cancel_requested

    @classmethod
    def is_active_for_client(cls, execution: _ExecutionLike) -> bool:
        return execution.status in cls.ACTIVE_STATUSES and not execution.cancel_requested

    @classmethod
    def needs_terminal_reconciliation(cls, execution: _ExecutionLike) -> bool:
        return execution.status in cls.ACTIVE_STATUSES and execution.cancel_requested


generation_execution_state_contract = GenerationExecutionStateContract()
