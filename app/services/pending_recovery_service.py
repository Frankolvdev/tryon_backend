from __future__ import annotations

import json
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.generation_financial_record import GenerationFinancialRecord
from app.models.user import User

D = Decimal


class PendingRecoveryService:
    """Read-only view of generation charges that remain collectible.

    No billing formula is duplicated here. Values come from the immutable
    generation financial breakdown already produced by the runtime and ledger.
    """

    @staticmethod
    def _decimal(value: object) -> D:
        try:
            return D(str(value or 0))
        except Exception:
            return D("0")

    @staticmethod
    def _breakdown(record: GenerationFinancialRecord) -> dict:
        try:
            data = json.loads(record.breakdown_json or "{}")
            return data if isinstance(data, dict) else {}
        except (TypeError, ValueError):
            return {}

    def list_pending(self, db: Session) -> dict:
        rows = db.execute(
            select(GenerationFinancialRecord, User.email)
            .outerjoin(User, User.id == GenerationFinancialRecord.user_id)
            .order_by(GenerationFinancialRecord.created_at.asc())
        ).all()

        items: list[dict] = []
        total_tokens = 0
        total_infrastructure = D("0")
        total_profit_estimate = D("0")

        for record, email in rows:
            breakdown = self._breakdown(record)
            if not bool(
                breakdown.get("settlement_pending")
                or breakdown.get("result_locked")
            ):
                continue

            charged = max(
                int(
                    breakdown.get("tokens_actually_charged")
                    or record.tokens_consumed
                    or 0
                ),
                0,
            )
            estimated_final = max(
                int(
                    breakdown.get("estimated_final_tokens")
                    or breakdown.get("final_tokens")
                    or charged
                ),
                charged,
            )
            pending_tokens = max(
                int(
                    breakdown.get("estimated_pending_tokens")
                    or breakdown.get("pending_tokens_not_charged")
                    or (estimated_final - charged)
                ),
                0,
            )

            infra_total = self._decimal(
                breakdown.get("infrastructure_cost_usd")
                if breakdown.get("infrastructure_cost_usd") is not None
                else record.infrastructure_cost_usd
            )
            covered = D("0")
            for bag in breakdown.get("token_bags_used") or []:
                covered += self._decimal(
                    bag.get("infrastructure_capacity_from_tokens_usd")
                    if bag.get("infrastructure_capacity_from_tokens_usd") is not None
                    else bag.get("infrastructure_capacity_used_usd")
                )
            infrastructure_pending = max(infra_total - covered, D("0"))

            desired_profit = self._decimal(breakdown.get("desired_profit_usd"))
            realized_profit = self._decimal(
                breakdown.get("profit_after_customer_benefits_usd")
                if breakdown.get("profit_after_customer_benefits_usd") is not None
                else breakdown.get("applied_profit_usd")
            )
            profit_pending_estimate = max(desired_profit - realized_profit, D("0"))
            economic_pending_estimate = infrastructure_pending + profit_pending_estimate

            total_tokens += pending_tokens
            total_infrastructure += infrastructure_pending
            total_profit_estimate += profit_pending_estimate

            items.append(
                {
                    "execution_id": record.execution_id,
                    "module_key": record.module_key,
                    "user_id": record.user_id,
                    "user_email": email,
                    "provider": breakdown.get("provider"),
                    "status": record.status,
                    "billing_access_status": breakdown.get("billing_access_status")
                    or "payment_pending",
                    "tokens_charged": charged,
                    "pending_tokens": pending_tokens,
                    "estimated_final_tokens": estimated_final,
                    "infrastructure_cost_usd": float(infra_total),
                    "infrastructure_covered_usd": float(covered),
                    "infrastructure_pending_usd": float(infrastructure_pending),
                    "profit_realized_usd": float(realized_profit),
                    "profit_pending_estimated_usd": float(profit_pending_estimate),
                    "economic_pending_estimated_usd": float(economic_pending_estimate),
                    "created_at": record.created_at,
                }
            )

        return {
            "items": items,
            "summary": {
                "pending_generations": len(items),
                "pending_tokens": total_tokens,
                "infrastructure_pending_usd": float(total_infrastructure),
                "profit_pending_estimated_usd": float(total_profit_estimate),
                "economic_pending_estimated_usd": float(
                    total_infrastructure + total_profit_estimate
                ),
            },
        }


pending_recovery_service = PendingRecoveryService()
