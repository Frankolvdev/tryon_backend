from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.generation_module_execution import GenerationModuleExecution
from app.models.user import User
from app.schemas.generation_module_runtime import GenerationModuleExecutionResponse
from app.services.generation_module_runtime_service import generation_module_runtime_service
from app.services.token_value_ledger_service import token_value_ledger_service
from app.services.promotional_credit_service import promotional_credit_service


@dataclass
class PendingSettlementRun:
    user_id: int
    trigger_source: str
    trigger_reference: str | None = None
    attempted: int = 0
    unlocked: int = 0
    tokens_debited: int = 0
    stopped_for_insufficient_balance: bool = False
    failed_execution_id: str | None = None
    errors: list[str] = field(default_factory=list)


class PendingGenerationSettlementService:
    """Best-effort continuation of already-created pending generation bills.

    This service intentionally does not implement billing mathematics. It only
    discovers persisted pending executions and delegates each settlement to the
    exact same runtime method used by the user's manual "unlock result" button.

    Paid token acquisition is committed before this service is called, so a
    technical failure here can never roll back or invalidate the purchase.
    """

    @staticmethod
    def _is_pending(execution: GenerationModuleExecutionResponse) -> bool:
        billing = execution.billing_breakdown or {}
        return bool(
            execution.result_locked
            or billing.get("result_locked")
            or billing.get("settlement_pending")
        )

    @staticmethod
    def _pending_tokens(execution: GenerationModuleExecutionResponse) -> int:
        billing = execution.billing_breakdown or {}
        explicit = execution.estimated_pending_tokens
        if explicit is None:
            explicit = billing.get("estimated_pending_tokens")
        if explicit is None:
            estimated_final = billing.get("estimated_final_tokens")
            if estimated_final is not None:
                explicit = max(
                    int(estimated_final) - int(execution.tokens_charged or 0),
                    0,
                )
        return max(int(explicit or 0), 0)

    def _pending_for_user(
        self,
        db: Session,
        *,
        user_id: int,
    ) -> list[GenerationModuleExecutionResponse]:
        rows = db.execute(
            select(GenerationModuleExecution)
            .where(
                GenerationModuleExecution.user_id == user_id,
                GenerationModuleExecution.status == "completed",
            )
            .order_by(
                GenerationModuleExecution.created_at.asc(),
                GenerationModuleExecution.id.asc(),
            )
        ).scalars().all()

        pending: list[GenerationModuleExecutionResponse] = []
        for row in rows:
            try:
                execution = GenerationModuleExecutionResponse.model_validate_json(
                    row.snapshot_json
                )
            except Exception:
                # A malformed historical snapshot must never block a paid token
                # purchase or the settlement of other valid executions.
                continue
            if self._is_pending(execution):
                pending.append(execution)
        return pending

    def settle_after_paid_credit(
        self,
        db: Session,
        *,
        user_id: int,
        trigger_source: str,
        trigger_reference: str | None = None,
    ) -> PendingSettlementRun:
        report = PendingSettlementRun(
            user_id=user_id,
            trigger_source=trigger_source,
            trigger_reference=trigger_reference,
        )

        # Lock the user's balance row. This serializes automatic settlements
        # for concurrent paid webhooks without changing the existing token/FIFO
        # services. The runtime settlement itself remains the single source of
        # truth for the debit and financial reconciliation.
        user = db.execute(
            select(User).where(User.id == user_id).with_for_update()
        ).scalar_one_or_none()
        if user is None:
            return report

        for execution in self._pending_for_user(db, user_id=user_id):
            pending_tokens = self._pending_tokens(execution)
            if pending_tokens <= 0:
                continue

            # Debts are FIFO and all-or-nothing per generation. If the oldest
            # debt cannot be paid completely, do not consume a partial amount
            # and do not skip ahead to newer debts.
            db.refresh(user)
            billing = execution.billing_breakdown or {}
            provider = str(billing.get("provider") or "") or None
            allow_promotional = promotional_credit_service.allow_pending_settlement(db)
            eligible_balance = token_value_ledger_service.eligible_token_balance(
                db, user_id=user_id, provider=provider, allow_promotional=allow_promotional,
            )
            if eligible_balance < pending_tokens:
                report.stopped_for_insufficient_balance = True
                break

            report.attempted += 1
            before = int(execution.tokens_charged or 0)
            try:
                updated = generation_module_runtime_service.settle_pending_billing(
                    db,
                    UUID(str(execution.id)),
                    user_id=user_id,
                )
            except Exception as exc:
                # The paid credit has already been committed by the caller.
                # Roll back only this best-effort settlement attempt and leave
                # the existing manual unlock endpoint available as fallback.
                db.rollback()
                report.failed_execution_id = str(execution.id)
                report.errors.append(str(exc))
                break

            if self._is_pending(updated):
                report.stopped_for_insufficient_balance = True
                break

            after = int(updated.tokens_charged or 0)
            report.unlocked += 1
            report.tokens_debited += max(after - before, 0)

        return report


pending_generation_settlement_service = PendingGenerationSettlementService()
