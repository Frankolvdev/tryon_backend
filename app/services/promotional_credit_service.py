from __future__ import annotations

import json
from decimal import Decimal, ROUND_FLOOR

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.exceptions import ConflictException, NotFoundException
from app.models.promotional_credit import (
    PromotionalCreditFund,
    PromotionalCreditReturn,
    PromotionalTokenGrant,
)
from app.models.system_setting import SystemSetting
from app.models.token_consumption_allocation import TokenConsumptionAllocation
from app.models.token_value_lot import TokenValueLot
from app.models.user import User
from app.repositories.system_setting_repository import system_setting_repository
from app.services.financial_protection_service import financial_protection_service
from app.services.pricing_service import pricing_service
from app.services.token_financial_snapshot_service import token_financial_snapshot_service
from app.services.token_service import token_service
from app.services.token_value_ledger_service import token_value_ledger_service

D = Decimal
PROMO_SOURCE = "promotional_credit"


class PromotionalCreditService:
    SETTING_SPECS = {
        "promotional_signup_enabled": ("boolean", False, "Créditos promocionales al registrarse", "Entregar tokens respaldados por la caja promocional a nuevos usuarios."),
        "free_signup_tokens": ("integer", 0, "Tokens promocionales por registro", "Cantidad máxima de tokens promocionales respaldados que recibe cada nuevo usuario."),
        "promotional_signup_provider": ("string", "general", "Proveedor promocional de registro", "Proveedor cuya caja promocional respalda los tokens de registro."),
        "promotional_allow_pending_settlement": ("boolean", False, "Permitir promocionales para deudas anteriores", "Permite usar bolsas promocionales para desbloquear generaciones que ya estaban pendientes."),
    }

    @staticmethod
    def normalize_provider(value: str | None) -> str:
        raw = str(value or "general").strip().lower().replace("-", "_")
        aliases = {
            "runpod_serverless": "runpod",
            "runpod": "runpod",
            "modal": "modal",
            "beam": "beam",
            "general": "general",
            "any": "general",
        }
        return aliases.get(raw, raw or "general")

    def infrastructure_reserve_per_token(self, db: Session) -> D:
        """USD reserved from the promotional pool for each granted token.

        Promotional tokens carry zero company profit, so the full commercial
        token value is provider funding. The ordinary generation pricing reserve
        (token value - protected profit) is still frozen separately in the token
        lot so generation token math remains identical to commercial tokens.
        """
        report = financial_protection_service.report(db)
        financial_protection_service.assert_report_safe(report, action="fund promotional tokens")
        token_value = D(str(pricing_service._token_value(db))).quantize(D("0.000000001"))
        if token_value <= 0:
            raise ConflictException("The commercial token value must be positive.")
        return token_value

    def generation_infrastructure_reserve_per_token(self, db: Session) -> D:
        report = financial_protection_service.report(db)
        financial_protection_service.assert_report_safe(report, action="fund promotional tokens")
        reserve = token_financial_snapshot_service.generation_infrastructure_capacity(
            token_value_usd=pricing_service._token_value(db),
            normal_profit_per_token_usd=report.safe_profit_per_token_usd or 0,
        ).quantize(D("0.000000001"))
        return reserve

    def _ensure_settings(self, db: Session) -> None:
        for order, (key, (value_type, default, label, description)) in enumerate(self.SETTING_SPECS.items(), start=60):
            if system_setting_repository.get_by_key(db, key):
                continue
            kwargs = dict(
                category="tokens", key=key, label=label, description=description,
                value_type=value_type, is_public=False, is_editable=True,
                is_sensitive=False, requires_restart=False, sort_order=order,
            )
            if value_type == "boolean":
                kwargs.update(value_boolean=bool(default), default_value_boolean=bool(default))
            elif value_type == "integer":
                kwargs.update(value_integer=int(default), default_value_integer=int(default))
            else:
                kwargs.update(value_string=str(default), default_value_string=str(default))
            db.add(SystemSetting(**kwargs))
        db.flush()

    def settings(self, db: Session) -> dict:
        self._ensure_settings(db)
        def value(key: str):
            row = system_setting_repository.get_by_key(db, key)
            typ = self.SETTING_SPECS[key][0]
            if typ == "boolean": return bool(row.value_boolean)
            if typ == "integer": return int(row.value_integer or 0)
            return str(row.value_string or self.SETTING_SPECS[key][1])
        return {
            "signup_enabled": value("promotional_signup_enabled"),
            "signup_tokens": value("free_signup_tokens"),
            "signup_provider": self.normalize_provider(value("promotional_signup_provider")),
            "allow_pending_settlement": value("promotional_allow_pending_settlement"),
        }

    def update_settings(self, db: Session, *, signup_enabled: bool, signup_tokens: int, signup_provider: str, allow_pending_settlement: bool) -> dict:
        self._ensure_settings(db)
        updates = {
            "promotional_signup_enabled": bool(signup_enabled),
            "free_signup_tokens": max(int(signup_tokens), 0),
            "promotional_signup_provider": self.normalize_provider(signup_provider),
            "promotional_allow_pending_settlement": bool(allow_pending_settlement),
        }
        for key, val in updates.items():
            row = system_setting_repository.get_by_key(db, key)
            typ = self.SETTING_SPECS[key][0]
            if typ == "boolean": row.value_boolean = bool(val)
            elif typ == "integer": row.value_integer = int(val)
            else: row.value_string = str(val)
            db.add(row)
        db.flush()
        return self.settings(db)

    def allow_pending_settlement(self, db: Session) -> bool:
        return bool(self.settings(db)["allow_pending_settlement"])

    def add_fund(self, db: Session, *, amount_usd: float, provider: str, reference: str | None, description: str | None, created_by_user_id: int | None) -> PromotionalCreditFund:
        amount = D(str(amount_usd)).quantize(D("0.000001"))
        if amount <= 0:
            raise ConflictException("Promotional credit amount must be greater than zero.")
        row = PromotionalCreditFund(
            provider=self.normalize_provider(provider), original_usd=amount, remaining_usd=amount,
            reference=(str(reference).strip() or None) if reference is not None else None,
            description=(str(description).strip() or None) if description is not None else None,
            created_by_user_id=created_by_user_id,
        )
        db.add(row); db.flush(); return row

    def _funds(self, db: Session, provider: str, *, lock: bool = False) -> list[PromotionalCreditFund]:
        normalized = self.normalize_provider(provider)
        query = select(PromotionalCreditFund).where(
            PromotionalCreditFund.provider == normalized,
            PromotionalCreditFund.remaining_usd > 0,
        ).order_by(PromotionalCreditFund.created_at, PromotionalCreditFund.id)
        if lock: query = query.with_for_update()
        return list(db.execute(query).scalars().all())

    def available_tokens(self, db: Session, provider: str) -> int:
        reserve = self.infrastructure_reserve_per_token(db)
        return sum(
            max(int((D(str(x.remaining_usd or 0)) / reserve).to_integral_value(rounding=ROUND_FLOOR)), 0)
            for x in self._funds(db, provider)
        )

    def _commercial_snapshot(self, db: Session, *, provider: str, funding_per_token: D) -> dict:
        generation_reserve=self.generation_infrastructure_reserve_per_token(db)
        snapshot = token_financial_snapshot_service.build_commercial_terms(
            token_value_usd=pricing_service._token_value(db),
            normal_profit_per_token_usd=0,
            profit_discount_percent=0,
            operational_reserve_per_token_usd=0,
            source_label="Crédito promocional",
            benefit_source="promotional_credit",
            benefit_label="Crédito promocional financiado",
            promotional_credit_funded=True,
            promotional_provider=self.normalize_provider(provider),
            promotional_funding_per_token_usd=str(funding_per_token),
            customer_paid_usd="0",
        )
        # Promotional lots have zero company profit, but generation-token math
        # must use the same frozen AI reserve as commercial tokens.
        snapshot["infrastructure_capacity_per_token_usd"] = str(generation_reserve)
        snapshot["infrastructure_reserve_source"] = "promotional_credit_pool"
        return snapshot

    def grant(self, db: Session, *, user_id: int, tokens: int, provider: str, grant_type: str, created_by_user_id: int | None = None, allow_partial: bool = False) -> dict:
        requested = max(int(tokens), 0)
        if requested <= 0:
            return {"requested_tokens": requested, "granted_tokens": 0, "provider": self.normalize_provider(provider), "amount_reserved_usd": 0.0}
        user = db.execute(select(User).where(User.id == user_id).with_for_update()).scalar_one_or_none()
        if not user: raise NotFoundException("User not found.")
        provider = self.normalize_provider(provider)
        reserve = self.infrastructure_reserve_per_token(db)
        funds = self._funds(db, provider, lock=True)
        available = sum((D(str(x.remaining_usd or 0)) for x in funds), D("0"))
        max_tokens = sum(
            int((D(str(x.remaining_usd or 0)) / reserve).to_integral_value(rounding=ROUND_FLOOR))
            for x in funds
        ) if reserve > 0 else 0
        grant_tokens = min(requested, max_tokens) if allow_partial else requested
        if grant_tokens <= 0:
            return {"requested_tokens": requested, "granted_tokens": 0, "provider": provider, "amount_reserved_usd": 0.0}
        if not allow_partial and max_tokens < requested:
            raise ConflictException(f"The {provider} promotional pool can fund only {max_tokens} token(s).")

        # One wallet credit, then one immutable promotional token lot per funding entry.
        token_service.credit_tokens(
            db, user_id=user_id, amount=grant_tokens, source=PROMO_SOURCE,
            reference_id=None, description=f"Promotional tokens ({grant_type}, {provider}).",
            commit=False, create_value_lot=False,
        )
        remaining_tokens = grant_tokens
        total_reserved = D("0")
        grant_rows: list[PromotionalTokenGrant] = []
        for fund in funds:
            if remaining_tokens <= 0: break
            fund_available = D(str(fund.remaining_usd or 0))
            fund_tokens = int((fund_available / reserve).to_integral_value(rounding=ROUND_FLOOR))
            take = min(remaining_tokens, max(fund_tokens, 0))
            if take <= 0: continue
            reserved = (reserve * take).quantize(D("0.000001"))
            lot = token_value_ledger_service.create_lot(
                db, user_id=user_id, tokens=take, source=PROMO_SOURCE,
                reference_id=f"promo-fund:{fund.id}", amount_paid_usd=0.0,
                metadata=self._commercial_snapshot(db, provider=provider, funding_per_token=reserve),
            )
            fund.remaining_usd = (fund_available - reserved).quantize(D("0.000001"))
            db.add(fund)
            grant = PromotionalTokenGrant(
                fund_id=fund.id, lot_id=lot.id, user_id=user_id, tokens_granted=take,
                reserve_per_token_usd=reserve, amount_reserved_usd=reserved,
                grant_type=grant_type, created_by_user_id=created_by_user_id,
            )
            db.add(grant); db.flush(); grant_rows.append(grant)
            total_reserved += reserved; remaining_tokens -= take
        if remaining_tokens:
            raise ConflictException("Promotional funding changed during the grant; no partial unbacked tokens were created.")
        return {
            "requested_tokens": requested, "granted_tokens": grant_tokens,
            "provider": provider, "amount_reserved_usd": float(total_reserved),
            "user_balance": int(user.token_balance), "grant_ids": [x.id for x in grant_rows],
        }

    def grant_signup(self, db: Session, *, user_id: int) -> dict:
        cfg = self.settings(db)
        if not cfg["signup_enabled"] or int(cfg["signup_tokens"] or 0) <= 0:
            return {"requested_tokens": 0, "granted_tokens": 0, "provider": cfg["signup_provider"], "amount_reserved_usd": 0.0}
        return self.grant(
            db, user_id=user_id, tokens=int(cfg["signup_tokens"]), provider=cfg["signup_provider"],
            grant_type="signup", created_by_user_id=None, allow_partial=True,
        )

    def return_for_expired_lot(self, db: Session, *, lot: TokenValueLot, remaining_tokens: int) -> D:
        if lot.source != PROMO_SOURCE or remaining_tokens <= 0:
            return D("0")
        grant = db.execute(select(PromotionalTokenGrant).where(PromotionalTokenGrant.lot_id == lot.id).with_for_update()).scalar_one_or_none()
        if not grant: return D("0")
        reference = str(lot.id)
        existing = db.execute(select(PromotionalCreditReturn).where(
            PromotionalCreditReturn.grant_id == grant.id,
            PromotionalCreditReturn.reason == "expiration",
            PromotionalCreditReturn.reference_id == reference,
        )).scalar_one_or_none()
        if existing: return D(str(existing.amount_usd or 0))
        amount = (D(str(grant.reserve_per_token_usd)) * int(remaining_tokens)).quantize(D("0.000001"))
        if amount <= 0: return D("0")
        fund = db.execute(select(PromotionalCreditFund).where(PromotionalCreditFund.id == grant.fund_id).with_for_update()).scalar_one()
        fund.remaining_usd = min(D(str(fund.original_usd)), D(str(fund.remaining_usd or 0)) + amount)
        db.add(fund)
        db.add(PromotionalCreditReturn(fund_id=fund.id, grant_id=grant.id, amount_usd=amount, reason="expiration", reference_id=reference))
        db.flush(); return amount

    def settle_execution_surplus(
        self,
        db: Session,
        *,
        execution_id: str,
        infrastructure_cost_usd: float,
        pricing_rounding_surplus_usd: float,
    ) -> dict:
        """Return unused provider-sponsored value and isolate company rounding.

        A promotional token reserves its full commercial token value because it
        contains zero company profit. Generation token quantity still uses the
        ordinary pricing rule. After the execution, only the promotional token's
        pro-rata real provider cost remains consumed; every unused sponsored cent
        returns to the same promotional fund. Commercial rounding remains company
        money and is never mixed into the promotional pool.
        """
        rows = db.execute(
            select(TokenConsumptionAllocation, TokenValueLot)
            .join(TokenValueLot, TokenValueLot.id == TokenConsumptionAllocation.lot_id)
            .where(TokenConsumptionAllocation.execution_id == execution_id)
            .order_by(TokenConsumptionAllocation.id)
        ).all()
        net_rows=[]
        total_tokens=0
        promo_tokens=0
        for allocation,lot in rows:
            net=max(int(allocation.tokens_allocated or 0)-int(allocation.tokens_reversed or 0),0)
            if net<=0:continue
            net_rows.append((allocation,lot,net)); total_tokens+=net
            if lot.source==PROMO_SOURCE: promo_tokens+=net
        if total_tokens<=0 or promo_tokens<=0:
            return {
                "promotional_credit_returned_usd":0.0,
                "company_rounding_surplus_usd":max(float(pricing_rounding_surplus_usd or 0),0.0),
            }

        infra=max(D(str(infrastructure_cost_usd or 0)),D("0"))
        returned=D("0")
        for _allocation,lot,net in net_rows:
            if lot.source!=PROMO_SOURCE:continue
            grant=db.execute(
                select(PromotionalTokenGrant)
                .where(PromotionalTokenGrant.lot_id==lot.id)
                .with_for_update()
            ).scalar_one_or_none()
            if not grant:continue
            reference=str(execution_id)
            existing=db.execute(select(PromotionalCreditReturn).where(
                PromotionalCreditReturn.grant_id==grant.id,
                PromotionalCreditReturn.reason=="execution_surplus",
                PromotionalCreditReturn.reference_id==reference,
            )).scalar_one_or_none()
            if existing:
                returned+=D(str(existing.amount_usd or 0));continue
            sponsored=(D(str(grant.reserve_per_token_usd))*net).quantize(D("0.000001"))
            actual_share=(infra*D(net)/D(total_tokens)).quantize(D("0.000001"))
            amount=max(sponsored-actual_share,D("0")).quantize(D("0.000001"))
            if amount<=0:continue
            fund=db.execute(
                select(PromotionalCreditFund)
                .where(PromotionalCreditFund.id==grant.fund_id)
                .with_for_update()
            ).scalar_one()
            fund.remaining_usd=min(D(str(fund.original_usd)),D(str(fund.remaining_usd or 0))+amount)
            db.add(fund)
            db.add(PromotionalCreditReturn(
                fund_id=fund.id,grant_id=grant.id,amount_usd=amount,
                reason="execution_surplus",reference_id=reference,
            ))
            returned+=amount

        commercial_share=D(total_tokens-promo_tokens)/D(total_tokens)
        company_rounding=(
            max(D(str(pricing_rounding_surplus_usd or 0)),D("0"))*commercial_share
        ).quantize(D("0.000001"))
        db.flush()
        return {
            "promotional_credit_returned_usd":float(returned),
            "company_rounding_surplus_usd":float(company_rounding),
        }

    def summary(self, db: Session) -> dict:
        reserve = self.infrastructure_reserve_per_token(db)
        generation_reserve = self.generation_infrastructure_reserve_per_token(db)
        funds = list(db.execute(select(PromotionalCreditFund).order_by(PromotionalCreditFund.created_at.desc(), PromotionalCreditFund.id.desc())).scalars().all())
        grants = list(db.execute(select(PromotionalTokenGrant).order_by(PromotionalTokenGrant.created_at.desc(), PromotionalTokenGrant.id.desc()).limit(100)).scalars().all())
        by_provider: dict[str, dict] = {}
        for fund in funds:
            row = by_provider.setdefault(fund.provider, {"provider": fund.provider, "funded_usd": 0.0, "available_usd": 0.0, "available_tokens": 0})
            row["funded_usd"] += float(fund.original_usd or 0); row["available_usd"] += float(fund.remaining_usd or 0)
        for row in by_provider.values():
            row["available_tokens"] = self.available_tokens(db, row["provider"])
        total_funded = sum(float(x.original_usd or 0) for x in funds)
        total_available = sum(float(x.remaining_usd or 0) for x in funds)
        users_by_id = {u.id: u.email for u in db.execute(select(User).where(User.id.in_({g.user_id for g in grants}))).scalars().all()} if grants else {}
        return {
            "reserve_per_token_usd": float(reserve),
            "generation_infrastructure_reserve_per_token_usd": float(generation_reserve),
            "total_funded_usd": total_funded,
            "total_available_usd": total_available,
            "provider_balances": sorted(by_provider.values(), key=lambda x: x["provider"]),
            "settings": self.settings(db),
            "funds": [{"id":x.id,"provider":x.provider,"original_usd":float(x.original_usd),"remaining_usd":float(x.remaining_usd),"reference":x.reference,"description":x.description,"created_at":x.created_at} for x in funds[:100]],
            "grants": [{"id":g.id,"fund_id":g.fund_id,"lot_id":g.lot_id,"user_id":g.user_id,"user_email":users_by_id.get(g.user_id),"tokens_granted":g.tokens_granted,"reserve_per_token_usd":float(g.reserve_per_token_usd),"amount_reserved_usd":float(g.amount_reserved_usd),"grant_type":g.grant_type,"created_at":g.created_at} for g in grants],
        }


promotional_credit_service = PromotionalCreditService()
