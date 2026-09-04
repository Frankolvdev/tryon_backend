from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.finance_withdrawal import FinanceWithdrawal
from app.models.infrastructure_funding import InfrastructureFundingMovement
from app.models.operational_expense import OperationalExpense
from app.models.token_value_lot import TokenValueLot
from app.models.user import User
from app.services.finance_cashbox_service import finance_cashbox_service
from app.services.operational_cashbox_service import operational_cashbox_service
from app.services.pending_recovery_service import pending_recovery_service
from app.services.token_value_ledger_service import token_value_ledger_service

D = Decimal
Q = D("0.000001")


class FinanceCashboxMovementService:
    """Read-only audit views for the cards shown in Caja y bolsas.

    The service deliberately does not create a second financial ledger.  Every
    movement is derived from the same persisted lots, executions, withdrawals,
    provider fundings and operating expenses that already build the card totals.
    This avoids a parallel balance that could drift from the financial source of
    truth.
    """

    LABELS = {
        "utility": "Dinero libre para ti",
        "infrastructure_cash": "IA aún en tu caja",
        "infrastructure_funded": "IA ya enviada",
        "pending_recovery": "Cobros pendientes",
        "blocked_profit": "Ganancia todavía en espera",
        "withdrawals": "Dinero ya retirado",
        "operational": "Gastos disponibles",
    }

    @staticmethod
    def _q(value: Any) -> D:
        return D(str(value or 0)).quantize(Q)

    @staticmethod
    def _movement(*, movement_id: str, at, kind: str, label: str, amount: D,
                  source_type: str, source_id: str | None = None,
                  lot_id: int | None = None, execution_id: str | None = None,
                  provider: str | None = None, user_id: int | None = None,
                  user_email: str | None = None, details: dict | None = None) -> dict:
        return {
            "id": movement_id,
            "occurred_at": at,
            "movement_type": kind,
            "label": label,
            "amount_usd": float(amount),
            "balance_before_usd": 0.0,
            "balance_after_usd": 0.0,
            "source_type": source_type,
            "source_id": source_id,
            "lot_id": lot_id,
            "execution_id": execution_id,
            "provider": provider,
            "user_id": user_id,
            "user_email": user_email,
            "details": details or {},
        }

    def _finalize(self, key: str, rows: list[dict], *, current: D, mode: str = "history", note: str | None = None) -> dict:
        rows.sort(key=lambda row: (row["occurred_at"], row["id"]))
        running = D("0")
        for row in rows:
            before = running
            running = self._q(running + D(str(row["amount_usd"])))
            row["balance_before_usd"] = float(before)
            row["balance_after_usd"] = float(running)
        return {
            "cashbox_key": key,
            "label": self.LABELS[key],
            "mode": mode,
            "current_balance_usd": float(self._q(current)),
            "reconstructed_balance_usd": float(self._q(running)),
            "reconciled": self._q(current) == self._q(running),
            "note": note,
            # newest first in UI while preserving before/after calculated chronologically
            "movements": list(reversed(rows)),
        }

    @staticmethod
    def _emails(db: Session) -> dict[int, str | None]:
        return {int(user_id): email for user_id, email in db.execute(select(User.id, User.email)).all()}

    def _commercial_lots(self, db: Session) -> list[TokenValueLot]:
        return db.execute(
            select(TokenValueLot)
            .where(TokenValueLot.source != "promotional_credit")
            .order_by(TokenValueLot.created_at, TokenValueLot.id)
        ).scalars().all()

    def _utility(self, db: Session, summary: dict, lots: list[TokenValueLot], emails: dict[int, str | None]) -> dict:
        rows: list[dict] = []
        for lot in lots:
            bag = finance_cashbox_service._bag_values(db, lot, emails.get(lot.user_id))
            released = self._q(bag["commercial_profit_released_usd"])
            if released > 0:
                at = lot.activated_at or lot.expired_at or lot.created_at
                rows.append(self._movement(
                    movement_id=f"profit:{lot.id}", at=at, kind="commercial_profit_release",
                    label=f"Ganancia liberada de bolsa #{lot.id}", amount=released,
                    source_type="token_bag", source_id=str(lot.id), lot_id=lot.id,
                    user_id=lot.user_id, user_email=emails.get(lot.user_id),
                    details={"source": bag["source_label"], "tokens": lot.original_tokens},
                ))

            generation_rows = sorted(finance_cashbox_service._generation_rows_for_bag(db, lot), key=lambda x: (x["created_at"], x["execution_id"]))
            remaining_profitability = self._q(bag.get("profitability_surplus_usd"))
            remaining_rounding = self._q(bag.get("rounding_surplus_usd"))
            for generation in generation_rows:
                raw_profitability = max(self._q(generation.get("profitability_surplus_usd")), D("0"))
                cash_profitability = min(raw_profitability, remaining_profitability)
                remaining_profitability -= cash_profitability
                if raw_profitability > 0:
                    rows.append(self._movement(
                        movement_id=f"profitability:{lot.id}:{generation['execution_id']}", at=generation["created_at"],
                        kind="profitability_surplus", label=f"Extra por mayor rentabilidad · {generation['execution_id']}",
                        amount=cash_profitability, source_type="generation", source_id=generation["execution_id"],
                        lot_id=lot.id, execution_id=generation["execution_id"], user_id=lot.user_id,
                        user_email=emails.get(lot.user_id), details={
                            "tokens_used": generation["tokens_used"],
                            "economic_surplus_usd": float(raw_profitability),
                            "cash_surplus_usd": float(cash_profitability),
                            "provider_held_usd": float(max(raw_profitability-cash_profitability,D("0"))),
                        },
                    ))
                raw_rounding = max(self._q(generation.get("rounding_surplus_usd")), D("0"))
                cash_rounding = min(raw_rounding, remaining_rounding)
                remaining_rounding -= cash_rounding
                if raw_rounding > 0:
                    rows.append(self._movement(
                        movement_id=f"rounding:{lot.id}:{generation['execution_id']}", at=generation["created_at"],
                        kind="rounding_surplus", label=f"Extra por redondeo · {generation['execution_id']}",
                        amount=cash_rounding, source_type="generation", source_id=generation["execution_id"],
                        lot_id=lot.id, execution_id=generation["execution_id"], user_id=lot.user_id,
                        user_email=emails.get(lot.user_id), details={
                            "tokens_used": generation["tokens_used"],
                            "economic_surplus_usd": float(raw_rounding),
                            "cash_surplus_usd": float(cash_rounding),
                            "provider_held_usd": float(max(raw_rounding-cash_rounding,D("0"))),
                        },
                    ))

            expiration = self._q(bag["expiration_release_usd"])
            if expiration > 0 and lot.expired_at:
                rows.append(self._movement(
                    movement_id=f"expiration:{lot.id}", at=lot.expired_at, kind="expiration_release",
                    label=f"Reserva IA liberada por vencimiento · bolsa #{lot.id}", amount=expiration,
                    source_type="token_bag", source_id=str(lot.id), lot_id=lot.id, user_id=lot.user_id,
                    user_email=emails.get(lot.user_id), details={"source": bag["source_label"]},
                ))

        for row in db.execute(select(FinanceWithdrawal).order_by(FinanceWithdrawal.withdrawn_at, FinanceWithdrawal.id)).scalars():
            rows.append(self._movement(
                movement_id=f"withdrawal:{row.id}", at=row.withdrawn_at, kind="withdrawal",
                label=row.concept or f"Retiro #{row.id}", amount=-self._q(row.amount_usd),
                source_type="withdrawal", source_id=str(row.id),
                details={"beneficiary": row.beneficiary, "method": row.method},
            ))
        return self._finalize("utility", rows, current=self._q(summary["available_usd"]))

    def _funded(self, db: Session, summary: dict) -> dict:
        rows = [
            self._movement(
                movement_id=f"funding:{row.id}", at=row.funded_at, kind="provider_funding",
                label=row.concept or f"Transferencia a {row.provider}", amount=self._q(row.amount_usd),
                source_type="infrastructure_funding", source_id=str(row.id), provider=row.provider,
                details={"beneficiary": row.beneficiary, "method": row.method},
            )
            for row in db.execute(select(InfrastructureFundingMovement).order_by(InfrastructureFundingMovement.funded_at, InfrastructureFundingMovement.id)).scalars()
        ]
        return self._finalize("infrastructure_funded", rows, current=self._q(summary["infrastructure_funded_usd"]))

    def _withdrawals(self, db: Session, summary: dict) -> dict:
        rows = [
            self._movement(
                movement_id=f"withdrawal-total:{row.id}", at=row.withdrawn_at, kind="withdrawal",
                label=row.concept or f"Retiro #{row.id}", amount=self._q(row.amount_usd),
                source_type="withdrawal", source_id=str(row.id),
                details={"beneficiary": row.beneficiary, "method": row.method},
            )
            for row in db.execute(select(FinanceWithdrawal).order_by(FinanceWithdrawal.withdrawn_at, FinanceWithdrawal.id)).scalars()
        ]
        return self._finalize("withdrawals", rows, current=self._q(summary["withdrawals_usd"]))

    def _blocked_profit(self, db: Session, summary: dict, lots: list[TokenValueLot], emails: dict[int, str | None]) -> dict:
        rows: list[dict] = []
        for lot in lots:
            snap = token_value_ledger_service._snapshot_for_lot(lot)
            total = self._q(snap["effective_profit_per_token"] * max(int(lot.original_tokens or 0), 0))
            if total <= 0:
                continue
            rows.append(self._movement(
                movement_id=f"blocked-open:{lot.id}", at=lot.created_at, kind="profit_blocked",
                label=f"Ganancia bloqueada al crear bolsa #{lot.id}", amount=total,
                source_type="token_bag", source_id=str(lot.id), lot_id=lot.id, user_id=lot.user_id,
                user_email=emails.get(lot.user_id),
            ))
            close_at = lot.refunded_at or lot.activated_at or lot.expired_at
            if close_at is not None or lot.status != "new":
                rows.append(self._movement(
                    movement_id=f"blocked-close:{lot.id}", at=close_at or lot.created_at,
                    kind="profit_unblocked", label=f"Ganancia dejó de estar en espera · bolsa #{lot.id}", amount=-total,
                    source_type="token_bag", source_id=str(lot.id), lot_id=lot.id, user_id=lot.user_id,
                    user_email=emails.get(lot.user_id), details={"final_status": lot.status},
                ))
        return self._finalize("blocked_profit", rows, current=self._q(summary["blocked_profit_usd"]))

    def _operational(self, db: Session, operational: dict, lots: list[TokenValueLot], emails: dict[int, str | None]) -> dict:
        rows: list[dict] = []
        for lot in lots:
            amount = self._q(getattr(lot, "released_operational_reserve_usd", 0))
            if amount <= 0 or not bool(getattr(lot, "operational_reserve_released", False)):
                continue
            at = lot.activated_at or lot.expired_at or lot.created_at
            rows.append(self._movement(
                movement_id=f"operational-release:{lot.id}", at=at, kind="operational_release",
                label=f"Fondo operativo liberado · bolsa #{lot.id}", amount=amount,
                source_type="token_bag", source_id=str(lot.id), lot_id=lot.id, user_id=lot.user_id,
                user_email=emails.get(lot.user_id),
            ))
        for expense in db.execute(select(OperationalExpense).order_by(OperationalExpense.spent_at, OperationalExpense.id)).scalars():
            rows.append(self._movement(
                movement_id=f"operational-expense:{expense.id}", at=expense.spent_at, kind="operational_expense",
                label=expense.concept, amount=-self._q(expense.amount_usd), source_type="operational_expense",
                source_id=str(expense.id), details={"category": expense.category, "beneficiary": expense.beneficiary, "method": expense.method},
            ))
        return self._finalize("operational", rows, current=self._q(operational["available_operational_funds_usd"]))

    def _pending(self, db: Session, summary: dict) -> dict:
        pending = pending_recovery_service.list_pending(db)
        rows = []
        for item in pending["items"]:
            amount = self._q(item["economic_pending_estimated_usd"])
            if amount <= 0:
                continue
            rows.append(self._movement(
                movement_id=f"pending:{item['execution_id']}", at=item["created_at"], kind="pending_recovery",
                label=f"Cobro pendiente · {item['module_key']}", amount=amount,
                source_type="generation", source_id=item["execution_id"], execution_id=item["execution_id"],
                provider=item.get("provider"), user_id=item.get("user_id"), user_email=item.get("user_email"),
                details={"pending_tokens": item["pending_tokens"], "infrastructure_pending_usd": item["infrastructure_pending_usd"], "profit_pending_estimated_usd": item["profit_pending_estimated_usd"]},
            ))
        return self._finalize(
            "pending_recovery", rows, current=self._q(summary["pending_recovery_economic_estimated_usd"]), mode="current_composition",
            note="Esta card es una obligación pendiente actual. El modal muestra las generaciones que componen el saldo de hoy; una generación conciliada deja de pertenecer a esta card.",
        )

    def _infrastructure_cash(self, db: Session, summary: dict, lots: list[TokenValueLot], emails: dict[int, str | None]) -> dict:
        rows: list[dict] = []
        for lot in lots:
            bag = finance_cashbox_service._bag_values(db, lot, emails.get(lot.user_id))
            amount = self._q(bag["infrastructure_unfunded_usd"])
            if amount <= 0:
                continue
            rows.append(self._movement(
                movement_id=f"ia-cash:{lot.id}", at=lot.created_at, kind="infrastructure_cash_obligation",
                label=f"IA que sigue en tu caja · bolsa #{lot.id}", amount=amount,
                source_type="token_bag", source_id=str(lot.id), lot_id=lot.id, user_id=lot.user_id,
                user_email=emails.get(lot.user_id), details={
                    "future_reserve_usd": bag["protected_infrastructure_remaining_usd"],
                    "infrastructure_used_usd": bag["infrastructure_used_usd"],
                    "funded_usd": bag["infrastructure_funded_usd"],
                },
            ))
        return self._finalize(
            "infrastructure_cash", rows, current=self._q(summary["infrastructure_cash_available_usd"]), mode="current_composition",
            note="Esta card representa el dinero de IA que aún debes conservar en tu caja. Se reconstruye por bolsa con la misma fórmula de fondeo usada por el saldo principal.",
        )

    def history(self, db: Session, key: str) -> dict:
        if key not in self.LABELS:
            raise ValueError("Unsupported finance cashbox key")
        # Keep expirations and historical repair behavior identical to the cards.
        summary = finance_cashbox_service.summary(db)
        lots = self._commercial_lots(db)
        emails = self._emails(db)
        if key == "utility":
            return self._utility(db, summary, lots, emails)
        if key == "infrastructure_cash":
            return self._infrastructure_cash(db, summary, lots, emails)
        if key == "infrastructure_funded":
            return self._funded(db, summary)
        if key == "pending_recovery":
            return self._pending(db, summary)
        if key == "blocked_profit":
            return self._blocked_profit(db, summary, lots, emails)
        if key == "withdrawals":
            return self._withdrawals(db, summary)
        operational = operational_cashbox_service.summary(db)
        return self._operational(db, operational, lots, emails)


finance_cashbox_movement_service = FinanceCashboxMovementService()
