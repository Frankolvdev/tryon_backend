from __future__ import annotations

from typing import Protocol


class _ExecutionLike(Protocol):
    status: str
    cancel_requested: bool
    provider_status: str | None


class GenerationExecutionStateContract:
    """Single execution-state policy shared by API exposure and recovery/dispatch.

    Backend supervision may keep a cancellation-pending execution attached until the
    provider confirms the terminal state. That does not make it dispatchable or an
    active generation for client UIs. Provider phases are a separate operational layer:
    they never add or replace a primary execution status.
    """

    ACTIVE_STATUSES = frozenset({"queued", "running"})
    TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})
    FINALIZING_PROVIDER_STATUS = "FINALIZING"

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

    @classmethod
    def is_finalizing(cls, execution: _ExecutionLike) -> bool:
        return (
            execution.status == "running"
            and str(getattr(execution, "provider_status", "") or "").upper()
            == cls.FINALIZING_PROVIDER_STATUS
        )

    @classmethod
    def is_provider_cancelable(cls, execution: _ExecutionLike) -> bool:
        """Whether a user cancellation can still stop provider work.

        FINALIZING means the provider already returned a successful result. Backend may
        still be materializing/persisting it, but cancelling there cannot save provider
        compute and risks discarding a valid paid result.
        """
        return (
            execution.status in cls.ACTIVE_STATUSES
            and not execution.cancel_requested
            and not cls.is_finalizing(execution)
        )


generation_execution_state_contract = GenerationExecutionStateContract()
