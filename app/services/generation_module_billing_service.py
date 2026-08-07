from __future__ import annotations

from sqlalchemy.orm import Session

from app.repositories.token_transaction_repository import token_transaction_repository
from app.services.token_service import token_service
from app.services.token_value_ledger_service import token_value_ledger_service


class GenerationModuleBillingService:
    debit_source = "generation_module"
    refund_source = "generation_module_refund"

    def charge(self, db: Session, *, user_id: int, execution_id: str, module_key: str, tokens: int, provider: str | None = None) -> None:
        if tokens <= 0:
            return
        existing = token_transaction_repository.get_by_source_reference(
            db, user_id=user_id, source=self.debit_source, reference_id=execution_id
        )
        if existing:
            return
        token_service.debit_tokens(
            db,
            user_id=user_id,
            amount=tokens,
            source=self.debit_source,
            reference_id=execution_id,
            description=f"Generation module '{module_key}' execution",
            allocation_reference=execution_id, allocation_provider=provider,
            allow_promotional=True, strict_allocation_eligibility=True,
        )

    def refund(self, db: Session, *, user_id: int, execution_id: str, module_key: str, tokens: int, reason: str) -> bool:
        if tokens <= 0:
            return False
        existing = token_transaction_repository.get_by_source_reference(
            db, user_id=user_id, source=self.refund_source, reference_id=execution_id
        )
        if existing:
            return False
        token_value_ledger_service.restore(db, execution_id=execution_id, tokens=tokens)
        token_service.credit_tokens(
            db,
            user_id=user_id,
            amount=tokens,
            source=self.refund_source,
            reference_id=execution_id,
            description=f"Refund for generation module '{module_key}': {reason}",
            create_value_lot=False,
        )
        return True

    def reconcile(
        self, db: Session, *, user_id: int, execution_id: str, module_key: str,
        previously_charged: int, final_tokens: int, reason: str,
        provider: str | None = None, allow_promotional: bool = True,
    ) -> tuple[int, int]:
        """Synchronously reconcile the upfront estimate before the result is exposed.

        Returns ``(extra_debited, refunded)`` and is idempotent through unique
        token transaction source/reference pairs.
        """
        previous = max(int(previously_charged), 0)
        final = max(int(final_tokens), 0)
        if final > previous:
            extra = final - previous
            source = "generation_module_adjustment"
            existing = token_transaction_repository.get_by_source_reference(
                db, user_id=user_id, source=source, reference_id=execution_id
            )
            if not existing:
                token_service.debit_tokens(
                    db, user_id=user_id, amount=extra, source=source,
                    reference_id=execution_id,
                    description=f"Final generation cost adjustment for '{module_key}': {reason}",
                    allocation_reference=execution_id, allocation_provider=provider,
                    allow_promotional=allow_promotional, strict_allocation_eligibility=True,
                )
                return extra, 0
        elif final < previous:
            refund = previous - final
            source = "generation_module_price_refund"
            existing = token_transaction_repository.get_by_source_reference(
                db, user_id=user_id, source=source, reference_id=execution_id
            )
            if not existing:
                token_value_ledger_service.restore(db, execution_id=execution_id, tokens=refund)
                token_service.credit_tokens(
                    db, user_id=user_id, amount=refund, source=source,
                    reference_id=execution_id,
                    description=f"Unused generation estimate returned for '{module_key}': {reason}",
                    create_value_lot=False,
                )
                return 0, refund
        return 0, 0


generation_module_billing_service = GenerationModuleBillingService()
