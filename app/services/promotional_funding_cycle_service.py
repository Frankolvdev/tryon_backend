from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.exceptions import ConflictException, NotFoundException
from app.common.time import utc_now
from app.models.promotional_credit import PromotionalCreditFund
from app.models.promotional_funding_cycle import PromotionalFundingCycle, PromotionalFundingSource

D = Decimal


class PromotionalFundingCycleService:
    """Recurring-credit policy layered on the existing promotional fund ledger.

    It never changes token pricing, grants, token lots, FIFO, or generation
    billing. Its only job is deciding which PromotionalCreditFund rows are
    currently eligible to finance NEW promotional grants.
    """

    @staticmethod
    def _money(value) -> D:
        return D(str(value or 0)).quantize(D("0.000001"))

    @staticmethod
    def _add_month(value: date) -> date:
        year = value.year + (1 if value.month == 12 else 0)
        month = 1 if value.month == 12 else value.month + 1
        day = min(value.day, monthrange(year, month)[1])
        return date(year, month, day)

    def _next_cycle_end(self, value: date, recurrence: str) -> date:
        """Return the next boundary from one anchor date.

        `current_cycle_end` remains persisted for auditability, but admins only
        provide a cycle start + periodicity.  No financial formula depends on
        this helper.
        """
        recurrence = str(recurrence or "monthly").strip().lower()
        if recurrence == "weekly":
            return value + timedelta(days=7)
        if recurrence == "quarterly":
            result = value
            for _ in range(3):
                result = self._add_month(result)
            return result
        if recurrence == "yearly":
            year = value.year + 1
            day = min(value.day, monthrange(year, value.month)[1])
            return date(year, value.month, day)
        if recurrence == "monthly":
            return self._add_month(value)
        raise ConflictException("Unsupported promotional credit periodicity.")

    def create_source(
        self,
        db: Session,
        *,
        name: str,
        provider: str,
        recurring_amount_usd: float,
        current_available_usd: float,
        cycle_start: date,
        recurrence: str = "monthly",
        simulation_enabled: bool = False,
        created_by_user_id: int | None = None,
    ) -> PromotionalFundingSource:
        recurring = self._money(recurring_amount_usd)
        opening = self._money(current_available_usd)
        if recurring <= 0:
            raise ConflictException("Recurring promotional credit must be greater than zero.")
        if opening < 0:
            raise ConflictException("Current promotional balance cannot be negative.")
        recurrence = str(recurrence or "monthly").strip().lower()
        cycle_end = self._next_cycle_end(cycle_start, recurrence)
        source_name = str(name or "").strip()
        if not source_name:
            raise ConflictException("Promotional funding source name is required.")

        source = PromotionalFundingSource(
            name=source_name,
            provider=str(provider).strip().lower(),
            source_type="recurring_provider",
            recurrence=recurrence,
            recurring_amount_usd=recurring,
            current_cycle_start=cycle_start,
            current_cycle_end=cycle_end,
            active=True,
            simulation_enabled=bool(simulation_enabled),
            created_by_user_id=created_by_user_id,
        )
        db.add(source)
        db.flush()
        self._create_cycle(
            db,
            source=source,
            cycle_start=cycle_start,
            cycle_end=cycle_end,
            opening_available=opening,
            configured_amount=recurring,
            first_cycle=True,
        )
        db.flush()
        return source

    def update_source(
        self,
        db: Session,
        *,
        source_id: int,
        name: str | None = None,
        recurring_amount_usd: float | None = None,
        recurrence: str | None = None,
        simulation_enabled: bool | None = None,
        active: bool | None = None,
    ) -> PromotionalFundingSource:
        source = db.execute(
            select(PromotionalFundingSource)
            .where(PromotionalFundingSource.id == source_id)
            .with_for_update()
        ).scalar_one_or_none()
        if source is None:
            raise NotFoundException("Promotional recurring funding source not found.")
        if name is not None:
            cleaned = str(name).strip()
            if not cleaned:
                raise ConflictException("Promotional funding source name is required.")
            source.name = cleaned
        if recurring_amount_usd is not None:
            recurring = self._money(recurring_amount_usd)
            if recurring <= 0:
                raise ConflictException("Recurring promotional credit must be greater than zero.")
            # Deliberately applies only to the NEXT cycle. The active cycle is immutable.
            source.recurring_amount_usd = recurring
        if recurrence is not None:
            cleaned_recurrence = str(recurrence).strip().lower()
            # Validate without changing the active cycle window.  A new
            # periodicity starts at the next rollover.
            self._next_cycle_end(source.current_cycle_end, cleaned_recurrence)
            source.recurrence = cleaned_recurrence
        if simulation_enabled is not None:
            source.simulation_enabled = bool(simulation_enabled)
        if active is not None:
            source.active = bool(active)
        source.updated_at = utc_now()
        db.add(source)
        db.flush()
        return source

    def _create_cycle(
        self,
        db: Session,
        *,
        source: PromotionalFundingSource,
        cycle_start: date,
        cycle_end: date,
        opening_available: D,
        configured_amount: D,
        first_cycle: bool,
    ) -> PromotionalFundingCycle:
        existing = db.execute(
            select(PromotionalFundingCycle).where(
                PromotionalFundingCycle.source_id == source.id,
                PromotionalFundingCycle.cycle_start == cycle_start,
                PromotionalFundingCycle.cycle_end == cycle_end,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing

        fund_id = None
        if opening_available > 0:
            fund = PromotionalCreditFund(
                provider=source.provider,
                original_usd=opening_available,
                remaining_usd=opening_available,
                reference=f"recurring-source:{source.id}:{cycle_start.isoformat()}",
                description=(
                    f"{source.name} · {'saldo real del primer ciclo' if first_cycle else 'renovación automática'} "
                    f"{cycle_start.isoformat()} → {cycle_end.isoformat()}"
                ),
                created_by_user_id=source.created_by_user_id,
            )
            db.add(fund)
            db.flush()
            fund_id = fund.id

        cycle = PromotionalFundingCycle(
            source_id=source.id,
            fund_id=fund_id,
            cycle_start=cycle_start,
            cycle_end=cycle_end,
            configured_amount_usd=configured_amount,
            opening_available_usd=opening_available,
            expired_unused_usd=D("0"),
            returned_after_close_usd=D("0"),
            status="active",
        )
        db.add(cycle)
        db.flush()
        return cycle

    def ensure_current_cycles(
        self,
        db: Session,
        *,
        today: date | None = None,
        source_id: int | None = None,
    ) -> int:
        """Lazy/idempotent rollover. Safe to call before every promo operation.

        No webhook is required. The first promotional action after a cycle end
        closes expired unused provider credit and opens as many missed monthly
        cycles as needed until the current date is covered.
        """
        today = today or utc_now().date()
        query = (
            select(PromotionalFundingSource)
            .where(PromotionalFundingSource.active.is_(True))
            .order_by(PromotionalFundingSource.id)
            .with_for_update()
        )
        if source_id is not None:
            query = query.where(PromotionalFundingSource.id == source_id)
        sources = list(db.execute(query).scalars().all())
        changed = 0
        for source in sources:
            guard = 0
            while today >= source.current_cycle_end:
                guard += 1
                if guard > 240:
                    raise ConflictException("Promotional cycle rollover exceeded the safety limit.")
                active_cycle = db.execute(
                    select(PromotionalFundingCycle)
                    .where(
                        PromotionalFundingCycle.source_id == source.id,
                        PromotionalFundingCycle.status == "active",
                    )
                    .order_by(PromotionalFundingCycle.id.desc())
                    .with_for_update()
                ).scalars().first()
                if active_cycle is not None:
                    expired = D("0")
                    if active_cycle.fund_id is not None:
                        fund = db.execute(
                            select(PromotionalCreditFund)
                            .where(PromotionalCreditFund.id == active_cycle.fund_id)
                            .with_for_update()
                        ).scalar_one()
                        expired = self._money(fund.remaining_usd)
                        fund.remaining_usd = D("0")
                        db.add(fund)
                    active_cycle.expired_unused_usd = expired
                    active_cycle.status = "closed"
                    active_cycle.closed_at = utc_now()
                    db.add(active_cycle)

                next_start = source.current_cycle_end
                next_end = self._next_cycle_end(next_start, source.recurrence)
                recurring = self._money(source.recurring_amount_usd)
                self._create_cycle(
                    db,
                    source=source,
                    cycle_start=next_start,
                    cycle_end=next_end,
                    opening_available=recurring,
                    configured_amount=recurring,
                    first_cycle=False,
                )
                source.current_cycle_start = next_start
                source.current_cycle_end = next_end
                source.updated_at = utc_now()
                db.add(source)
                changed += 1
        if changed:
            db.flush()
        return changed

    def preview_next_cycle(
        self,
        db: Session,
        *,
        source_id: int,
    ) -> dict:
        """Dry-run exactly ONE next configured cycle. It never mutates money."""
        source = db.execute(
            select(PromotionalFundingSource).where(PromotionalFundingSource.id == source_id)
        ).scalar_one_or_none()
        if source is None:
            raise NotFoundException("Promotional recurring funding source not found.")
        if not source.simulation_enabled:
            raise ConflictException("Cycle simulation is disabled for this promotional source.")

        projected_start = source.current_cycle_end
        projected_end = self._next_cycle_end(projected_start, source.recurrence)
        return {
            "source_id": source.id,
            "source_name": source.name,
            "simulation": True,
            "effective_date": projected_start,
            "changed_cycles": 0,
            "would_roll_cycles": 1,
            "current_cycle_start": source.current_cycle_start,
            "current_cycle_end": source.current_cycle_end,
            "projected_cycle_start": projected_start,
            "projected_cycle_end": projected_end,
            "projected_opening_usd": float(source.recurring_amount_usd),
            "message": (
                f"Simulation only: the next cycle would be "
                f"{projected_start.isoformat()} to {projected_end.isoformat()} "
                f"with USD {float(source.recurring_amount_usd):.2f}. "
                "No balance or real cycle was changed."
            ),
        }

    def trigger_webhook(
        self,
        db: Session,
        *,
        source_id: int,
        simulation: bool = False,
    ) -> dict:
        """Manual/webhook entry point using the same idempotent rollover guard."""
        source = db.execute(
            select(PromotionalFundingSource).where(PromotionalFundingSource.id == source_id)
        ).scalar_one_or_none()
        if source is None:
            raise NotFoundException("Promotional recurring funding source not found.")

        if simulation:
            return self.preview_next_cycle(db, source_id=source_id)

        effective_date = utc_now().date()
        changed = self.ensure_current_cycles(db, today=effective_date, source_id=source_id)
        item = next((x for x in self.summary(db) if x["id"] == source_id), None)
        if item is None:
            raise NotFoundException("Promotional recurring funding source not found.")
        return {
            "source_id": source.id,
            "source_name": source.name,
            "simulation": False,
            "effective_date": effective_date,
            "changed_cycles": changed,
            "would_roll_cycles": changed,
            "current_cycle_start": item["current_cycle_start"],
            "current_cycle_end": item["current_cycle_end"],
            "projected_cycle_start": item["current_cycle_start"],
            "projected_cycle_end": item["current_cycle_end"],
            "projected_opening_usd": None,
            "message": (
                f"Cycle webhook applied: {changed} cycle(s) renewed."
                if changed
                else "Cycle webhook checked successfully. The current cycle is still active."
            ),
        }

    def _cycle_rows(self, db: Session) -> list[PromotionalFundingCycle]:
        return list(db.execute(select(PromotionalFundingCycle)).scalars().all())

    def ordered_eligible_funds(self, db: Session, *, provider: str, lock: bool = False) -> list[PromotionalCreditFund]:
        self.ensure_current_cycles(db)
        normalized = str(provider or "general").strip().lower()
        today = utc_now().date()
        cycles = self._cycle_rows(db)
        cycle_by_fund = {c.fund_id: c for c in cycles if c.fund_id is not None}
        active_source_ids = set(db.execute(
            select(PromotionalFundingSource.id).where(PromotionalFundingSource.active.is_(True))
        ).scalars().all())

        query = select(PromotionalCreditFund).where(
            PromotionalCreditFund.provider == normalized,
            PromotionalCreditFund.remaining_usd > 0,
        )
        if lock:
            query = query.with_for_update()
        rows = list(db.execute(query).scalars().all())

        recurring: list[tuple[date, PromotionalCreditFund]] = []
        own: list[PromotionalCreditFund] = []
        for fund in rows:
            cycle = cycle_by_fund.get(fund.id)
            if cycle is None:
                own.append(fund)  # every historical/manual fund remains company-owned funding
                continue
            if (
                cycle.status == "active"
                and cycle.source_id in active_source_ids
                and cycle.cycle_start <= today < cycle.cycle_end
            ):
                recurring.append((cycle.cycle_end, fund))
            # Closed/future recurring funds are intentionally ineligible.

        recurring.sort(key=lambda item: (item[0], item[1].created_at, item[1].id))
        own.sort(key=lambda fund: (fund.created_at, fund.id))
        return [fund for _end, fund in recurring] + own

    def restore_amount(self, db: Session, *, fund: PromotionalCreditFund, amount: D) -> bool:
        """Restore backing without resurrecting an expired provider cycle.

        Returns True when the amount is available again (own/current-cycle fund),
        False when it belongs to a provider cycle that has already closed.
        """
        amount = self._money(amount)
        if amount <= 0:
            return True
        cycle = db.execute(
            select(PromotionalFundingCycle)
            .where(PromotionalFundingCycle.fund_id == fund.id)
            .with_for_update()
        ).scalar_one_or_none()
        if cycle is not None and cycle.status != "active":
            # At close, unallocated money already expired. Only the part that had
            # actually been committed to grants is allowed to return later, and
            # it remains historical/unavailable instead of resurrecting credit.
            capacity = max(
                self._money(fund.original_usd)
                - self._money(cycle.expired_unused_usd)
                - self._money(cycle.returned_after_close_usd),
                D("0"),
            )
            if amount > capacity:
                raise ConflictException(
                    f"Closed promotional cycle #{cycle.id} cannot receive more backing than was committed before it closed."
                )
            cycle.returned_after_close_usd = self._money(cycle.returned_after_close_usd) + amount
            db.add(cycle)
            return False

        capacity = max(self._money(fund.original_usd) - self._money(fund.remaining_usd), D("0"))
        if amount > capacity:
            raise ConflictException(
                f"Promotional fund #{fund.id} cannot receive more backing than it originally committed."
            )
        fund.remaining_usd = self._money(fund.remaining_usd) + amount
        db.add(fund)
        return True

    def summary(self, db: Session) -> list[dict]:
        self.ensure_current_cycles(db)
        today = utc_now().date()
        sources = list(db.execute(
            select(PromotionalFundingSource).order_by(PromotionalFundingSource.created_at.desc(), PromotionalFundingSource.id.desc())
        ).scalars().all())
        cycles = list(db.execute(
            select(PromotionalFundingCycle).order_by(PromotionalFundingCycle.cycle_start.desc(), PromotionalFundingCycle.id.desc())
        ).scalars().all())
        funds_by_id = {
            f.id: f for f in db.execute(select(PromotionalCreditFund)).scalars().all()
        }
        by_source: dict[int, list[PromotionalFundingCycle]] = {}
        for cycle in cycles:
            by_source.setdefault(cycle.source_id, []).append(cycle)
        result=[]
        for source in sources:
            source_cycles = by_source.get(source.id, [])
            current = next((c for c in source_cycles if c.status == "active" and c.cycle_start <= today < c.cycle_end), None)
            current_available = D("0")
            if current and current.fund_id and current.fund_id in funds_by_id and source.active:
                current_available = self._money(funds_by_id[current.fund_id].remaining_usd)
            result.append({
                "id": source.id,
                "name": source.name,
                "provider": source.provider,
                "source_type": source.source_type,
                "recurrence": source.recurrence,
                "recurring_amount_usd": float(source.recurring_amount_usd),
                "current_cycle_start": source.current_cycle_start,
                "current_cycle_end": source.current_cycle_end,
                "current_available_usd": float(current_available),
                "active": bool(source.active),
                "simulation_enabled": bool(source.simulation_enabled),
                "cycles": [{
                    "id": c.id,
                    "cycle_start": c.cycle_start,
                    "cycle_end": c.cycle_end,
                    "configured_amount_usd": float(c.configured_amount_usd),
                    "opening_available_usd": float(c.opening_available_usd),
                    "current_available_usd": float(funds_by_id[c.fund_id].remaining_usd) if c.fund_id and c.fund_id in funds_by_id and c.status == "active" and source.active else 0.0,
                    "expired_unused_usd": float(c.expired_unused_usd),
                    "returned_after_close_usd": float(c.returned_after_close_usd),
                    "status": c.status,
                } for c in source_cycles[:24]],
            })
        return result


promotional_funding_cycle_service = PromotionalFundingCycleService()
