from __future__ import annotations

from sqlalchemy.orm import Session

from app.repositories.token_transaction_repository import token_transaction_repository
from app.services.token_service import token_service


class GenerationModuleBillingService:
    debit_source = "generation_module"
    refund_source = "generation_module_refund"

    def charge(self, db: Session, *, user_id: int, execution_id: str, module_key: str, tokens: int) -> None:
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
        )

    def refund(self, db: Session, *, user_id: int, execution_id: str, module_key: str, tokens: int, reason: str) -> bool:
        if tokens <= 0:
            return False
        existing = token_transaction_repository.get_by_source_reference(
            db, user_id=user_id, source=self.refund_source, reference_id=execution_id
        )
        if existing:
            return False
        token_service.credit_tokens(
            db,
            user_id=user_id,
            amount=tokens,
            source=self.refund_source,
            reference_id=execution_id,
            description=f"Refund for generation module '{module_key}': {reason}",
        )
        return True


generation_module_billing_service = GenerationModuleBillingService()
