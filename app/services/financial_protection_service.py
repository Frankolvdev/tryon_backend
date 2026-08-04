from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.common.exceptions import ConflictException
from app.models.billing_coupon import BillingCoupon
from app.models.generation_module import GenerationModule
from app.models.subscription_plan import SubscriptionPlan
from app.models.token_package import TokenPackage
from app.repositories.pricing_rule_repository import pricing_rule_repository
from app.schemas.financial_protection import (
    FinancialProtectionReport,
    FinancialProtectionRuleDiagnostic,
    ProtectedCommercialPrice,
)


class FinancialProtectionService:
    """Protects infrastructure by allowing discounts to consume profit only.

    This service deliberately does not read or recalculate GPU prices, durations,
    scaledown windows, technical margins, infrastructure cost, or execution time.
    The only financial input is PricingRule.desired_profit_usd.
    """

    def _profit_diagnostics(
        self,
        db: Session,
        *,
        rule_overrides: dict[int, dict[str, Any]] | None = None,
    ) -> list[FinancialProtectionRuleDiagnostic]:
        rule_overrides = rule_overrides or {}
        rows: list[FinancialProtectionRuleDiagnostic] = []
        for rule in pricing_rule_repository.list_all(db):
            override = rule_overrides.get(rule.id, {})
            active = bool(override.get("is_active", rule.is_active))
            module_id = override.get("generation_module_id", rule.generation_module_id)
            if not active or module_id is None:
                continue
            module = db.get(GenerationModule, module_id)
            if module is None or not module.is_active:
                continue
            profit = max(float(override.get("desired_profit_usd", rule.desired_profit_usd or 0)), 0.0)
            rows.append(FinancialProtectionRuleDiagnostic(
                pricing_rule_id=rule.id,
                generation_module_id=module.id,
                module_key=module.key,
                module_name=module.name,
                desired_profit_usd=round(profit, 9),
            ))
        if rows:
            limiting = min(rows, key=lambda item: item.desired_profit_usd)
            for row in rows:
                row.is_limiting = row.pricing_rule_id == limiting.pricing_rule_id
        return rows

    def _highest_active_discount(self, db: Session) -> float:
        values: list[float] = [0.0]
        for plan in db.query(SubscriptionPlan).filter(SubscriptionPlan.is_active.is_(True)).all():
            try:
                import json
                metadata = json.loads(plan.metadata_json or "{}")
            except (TypeError, ValueError):
                metadata = {}
            values.append(float(metadata.get("requested_discount_percent") or 0))
        for package in db.query(TokenPackage).filter(TokenPackage.is_active.is_(True)).all():
            values.append(float(package.requested_discount_percent or 0))
        for coupon in db.query(BillingCoupon).filter(BillingCoupon.is_active.is_(True)).all():
            if str(coupon.discount_type) == "percentage":
                values.append(float(coupon.percentage_off or 0))
        return max(values)

    def _profit_per_token_diagnostics(self, db: Session):
        from app.services.pricing_service import pricing_service
        applied = {item.rule_id: item for item in pricing_service.list_applied_rules(db)}
        rows = self._profit_diagnostics(db)
        enriched = []
        for row in rows:
            item = applied.get(row.pricing_rule_id)
            estimated_tokens = int(item.estimated_tokens or 0) if item else 0
            if estimated_tokens <= 0:
                continue
            enriched.append((row, row.desired_profit_usd / estimated_tokens, estimated_tokens))
        return enriched

    def report(self, db: Session, *, rule_overrides: dict[int, dict[str, Any]] | None = None, **_: Any) -> FinancialProtectionReport:
        diagnostics = self._profit_diagnostics(db, rule_overrides=rule_overrides)
        enriched = self._profit_per_token_diagnostics(db) if not rule_overrides else []
        warnings: list[str] = []

        # The limiting rule is ALWAYS the active rule with the smallest
        # desired_profit_usd. Estimated tokens are used only after selecting
        # that rule, to scale its protected profit across a commercial product.
        # They must never decide which rule is the highest-risk rule.
        limiting_diagnostic = (
            min(diagnostics, key=lambda item: item.desired_profit_usd)
            if diagnostics
            else None
        )
        enriched_by_rule_id = {item[0].pricing_rule_id: item for item in enriched}
        limiting = (
            enriched_by_rule_id.get(limiting_diagnostic.pricing_rule_id)
            if limiting_diagnostic is not None
            else None
        )
        safe_profit = (
            limiting_diagnostic.desired_profit_usd
            if limiting_diagnostic is not None
            else None
        )
        safe_profit_per_token = limiting[1] if limiting else None
        highest = self._highest_active_discount(db)
        status = "protected"
        if not diagnostics or not enriched:
            status = "not_configured"; warnings.append("No active pricing rule has a valid estimated token cost.")
        elif safe_profit_per_token is None or safe_profit_per_token <= 0:
            status = "blocked"; warnings.append("The limiting rule has no profit per token available.")
        elif highest > 100:
            status = "blocked"; warnings.append("An active commercial offer exceeds 100% of protected profit.")
        return FinancialProtectionReport(
            safe_profit_usd=round(safe_profit,9) if safe_profit is not None else None,
            safe_profit_per_token_usd=round(safe_profit_per_token,9) if safe_profit_per_token is not None else None,
            maximum_allowed_discount_percent=100.0,
            highest_active_discount_percent=round(highest,6),
            available_discount_percentage_points=round(max(0.0,100.0-highest),6),
            status=status,
            limiting_pricing_rule_id=limiting_diagnostic.pricing_rule_id if limiting_diagnostic else None,
            limiting_generation_module_id=limiting_diagnostic.generation_module_id if limiting_diagnostic else None,
            limiting_module_key=limiting_diagnostic.module_key if limiting_diagnostic else None,
            limiting_module_name=limiting_diagnostic.module_name if limiting_diagnostic else None,
            diagnostics=diagnostics,warnings=warnings,
        )

    def assert_report_safe(self, report: FinancialProtectionReport, *, action: str) -> None:
        if report.safe_profit_per_token_usd is None or report.safe_profit_per_token_usd <= 0:
            raise ConflictException(f"Cannot {action}: no active profit-per-token reference is configured.")
        if report.highest_active_discount_percent > 100 + 1e-9:
            raise ConflictException(f"Cannot {action}: an active discount exceeds 100% of protected profit.")

    def assert_rule_change(self, db: Session, rule_id: int, values: dict[str, Any], *, action: str) -> None:
        # Existing generation pricing remains authoritative; catalog repricing validates after changes.
        return None

    def assert_gpu_price_change(self, db: Session, **_: Any) -> None:
        return None

    def protected_price(self, db: Session, *, nominal_price_usd: float, requested_discount_percent: float, existing_discount_percent: float = 0.0, tokens_amount: int | None = None) -> ProtectedCommercialPrice:
        report=self.report(db); self.assert_report_safe(report,action="price commercial catalog")
        requested=float(requested_discount_percent); existing=max(float(existing_discount_percent),0.0); combined=existing+requested
        if requested < 0 or requested > 100: raise ConflictException("Discount must be between 0% and 100% of protected profit.")
        if combined > 100 + 1e-9:
            raise ConflictException(f"Combined discount cannot exceed 100% of protected profit. Maximum additional discount: {max(0,100-existing):.2f}%.")
        nominal=max(float(nominal_price_usd),0.0)
        token_count=max(int(tokens_amount or 0),0)
        profit_budget=float(report.safe_profit_per_token_usd or 0) * token_count
        discount_amount=profit_budget*requested/100.0
        if discount_amount > nominal + 1e-9: discount_amount=nominal
        final=nominal-discount_amount
        effective=(discount_amount/nominal*100) if nominal>0 else 0
        return ProtectedCommercialPrice(
            nominal_price_usd=round(nominal,6),requested_discount_percent=round(requested,6),effective_discount_percent=round(effective,6),
            maximum_allowed_discount_percent=round(max(0,100-existing),6),safe_profit_usd=round(profit_budget,9),
            safe_profit_per_token_usd=round(float(report.safe_profit_per_token_usd or 0),9),discounted_profit_usd=round(discount_amount,9),
            remaining_profit_usd=round(max(0,profit_budget*(100-combined)/100),9),discount_amount_usd=round(discount_amount,6),final_price_usd=round(final,6),
            potential_loss_usd=0,limiting_pricing_rule_id=report.limiting_pricing_rule_id,limiting_generation_module_id=report.limiting_generation_module_id,
            limiting_module_name=report.limiting_module_name,protected_discount_percent=100,calculated_maximum_safe_discount_percent=100,protection_limited=False,
        )


financial_protection_service = FinancialProtectionService()
