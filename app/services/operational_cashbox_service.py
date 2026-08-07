from __future__ import annotations

from decimal import Decimal
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.exceptions import ConflictException
from app.common.time import utc_now
from app.models.operational_expense import OperationalExpense
from app.models.system_setting import SystemSetting
from app.models.token_value_lot import TokenValueLot
from app.services.pricing_service import OPERATIONAL_RESERVE_KEY, pricing_service
from app.services.token_value_ledger_service import token_value_ledger_service

D = Decimal


class OperationalCashboxService:
    """Independent operating-expense cashbox backed by immutable lot snapshots.

    Income is never inferred from today's configuration. Every lot contributes
    only the operational component frozen when that lot was created. Historical
    lots therefore remain unchanged (normally USD 0). Promotional lots never
    contribute to company operating cash.
    """

    @staticmethod
    def _q(value: D) -> D:
        return D(str(value or 0)).quantize(D("0.000001"))

    def release_on_activation(self, lot: TokenValueLot, *, tokens_backed: int) -> D:
        if lot.source == "promotional_credit" or bool(getattr(lot, "operational_reserve_released", False)):
            return D("0")
        snapshot = token_value_ledger_service._snapshot_for_lot(lot)
        per_token = max(D(str(snapshot.get("operational_reserve_per_token") or 0)), D("0"))
        release = self._q(per_token * max(int(tokens_backed or 0), 0))
        lot.operational_reserve_released = True
        lot.released_operational_reserve_usd = release
        return release

    def release_on_expiration(self, lot: TokenValueLot, *, expired_tokens: int) -> D:
        if lot.source == "promotional_credit" or bool(getattr(lot, "operational_reserve_released", False)):
            return D("0")
        snapshot = token_value_ledger_service._snapshot_for_lot(lot)
        per_token = max(D(str(snapshot.get("operational_reserve_per_token") or 0)), D("0"))
        release = self._q(per_token * max(int(expired_tokens or 0), 0))
        lot.operational_reserve_released = True
        lot.released_operational_reserve_usd = release
        return release

    def summary(self, db: Session) -> dict:
        lots = db.execute(select(TokenValueLot).where(TokenValueLot.source != "promotional_credit")).scalars().all()
        released = D("0")
        blocked = D("0")
        lifetime = D("0")
        contributing = 0
        for lot in lots:
            snapshot = token_value_ledger_service._snapshot_for_lot(lot)
            per_token = max(D(str(snapshot.get("operational_reserve_per_token") or 0)), D("0"))
            if per_token <= 0:
                continue
            contributing += 1
            # Lifetime is informational. For non-refunded lots it represents the
            # operational component originally frozen in the commercial sale.
            if lot.status != "refunded":
                lifetime += self._q(per_token * max(int(lot.original_tokens or 0), 0))
            if bool(getattr(lot, "operational_reserve_released", False)):
                released += D(str(getattr(lot, "released_operational_reserve_usd", 0) or 0))
            elif lot.status not in {"refunded", "expired"}:
                # Still refundable/unactivated: only the tokens still belonging to
                # this lot are blocked. Partial refunds therefore cannot inflate it.
                blocked += self._q(per_token * max(int(lot.remaining_tokens or 0), 0))

        spent = D(str(db.execute(select(func.coalesce(func.sum(OperationalExpense.amount_usd), 0))).scalar_one() or 0))
        available = max(released - spent, D("0"))
        return {
            "operational_reserve_per_token_usd": float(pricing_service._operational_reserve(db)),
            "commercial_sale_value_per_token_usd": float(pricing_service._commercial_sale_value(db)),
            "lifetime_operational_funds_usd": float(self._q(lifetime)),
            "released_operational_funds_usd": float(self._q(released)),
            "blocked_operational_funds_usd": float(self._q(blocked)),
            "spent_operational_funds_usd": float(self._q(spent)),
            "available_operational_funds_usd": float(self._q(available)),
            "contributing_bags": contributing,
        }

    def expenses(self, db: Session):
        return db.execute(select(OperationalExpense).order_by(OperationalExpense.spent_at.desc(), OperationalExpense.id.desc())).scalars().all()

    def create_expense(self, db: Session, data, admin_id: int):
        # Serialize spending against the same configuration row that defines this
        # cashbox. This prevents two admins from spending the same available USD.
        setting = db.execute(
            select(SystemSetting).where(SystemSetting.key == OPERATIONAL_RESERVE_KEY).with_for_update()
        ).scalar_one_or_none()
        if setting is None:
            raise ConflictException("Operational reserve setting is missing. Seed default settings first.")
        amount = self._q(D(str(data.amount_usd)))
        available = self._q(D(str(self.summary(db)["available_operational_funds_usd"])))
        if amount > available:
            raise ConflictException(
                f"Operational cashbox has only USD {available:.6f} available."
            )
        row = OperationalExpense(
            amount_usd=amount, currency="USD", category=str(data.category).strip().lower(),
            beneficiary=data.beneficiary, concept=data.concept, method=data.method,
            proof_url=data.proof_url, notes=data.notes, created_by_user_id=admin_id,
            spent_at=data.spent_at or utc_now(),
        )
        db.add(row)
        db.flush()
        return row


operational_cashbox_service = OperationalCashboxService()
