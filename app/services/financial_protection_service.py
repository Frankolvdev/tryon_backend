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

    def report(
        self,
        db: Session,
        *,
        rule_overrides: dict[int, dict[str, Any]] | None = None,
        **_: Any,
    ) -> FinancialProtectionReport:
        diagnostics = self._profit_diagnostics(db, rule_overrides=rule_overrides)
        warnings: list[str] = []
        limiting = min(diagnostics, key=lambda item: item.desired_profit_usd) if diagnostics else None
        safe_profit = limiting.desired_profit_usd if limiting else None
        highest = self._highest_active_discount(db)
        if not diagnostics:
            status = "not_configured"
            warnings.append("No active pricing rules are applied to active generation modules.")
        elif safe_profit is None or safe_profit <= 0:
            status = "blocked"
            warnings.append("The limiting pricing rule has no desired profit available for discounts.")
        elif highest > 100:
            status = "blocked"
            warnings.append("An active commercial offer exceeds 100% of protected profit.")
        else:
            status = "protected"
        return FinancialProtectionReport(
            safe_profit_usd=round(safe_profit, 9) if safe_profit is not None else None,
            maximum_allowed_discount_percent=100.0,
            highest_active_discount_percent=round(highest, 6),
            available_discount_percentage_points=round(max(0.0, 100.0 - highest), 6),
            status=status,
            limiting_pricing_rule_id=limiting.pricing_rule_id if limiting else None,
            limiting_generation_module_id=limiting.generation_module_id if limiting else None,
            limiting_module_key=limiting.module_key if limiting else None,
            limiting_module_name=limiting.module_name if limiting else None,
            diagnostics=diagnostics,
            warnings=warnings,
        )

    def assert_report_safe(self, report: FinancialProtectionReport, *, action: str) -> None:
        if report.safe_profit_usd is None:
            raise ConflictException(f"Cannot {action}: no active desired profit is configured.")
        if report.safe_profit_usd <= 0:
            raise ConflictException(f"Cannot {action}: the limiting desired profit must be greater than zero.")
        if report.highest_active_discount_percent > 100 + 1e-9:
            raise ConflictException(f"Cannot {action}: an active discount exceeds 100% of protected profit.")

    def assert_rule_change(self, db: Session, rule_id: int, values: dict[str, Any], *, action: str) -> None:
        self.assert_report_safe(self.report(db, rule_overrides={rule_id: values}), action=action)

    def assert_gpu_price_change(self, db: Session, **_: Any) -> None:
        # GPU costs are intentionally outside profit-only discount protection.
        return None

    def protected_price(
        self,
        db: Session,
        *,
        nominal_price_usd: float,
        requested_discount_percent: float,
        existing_discount_percent: float = 0.0,
    ) -> ProtectedCommercialPrice:
        report = self.report(db)
        self.assert_report_safe(report, action="price commercial catalog")
        requested = float(requested_discount_percent)
        existing = max(float(existing_discount_percent), 0.0)
        combined = existing + requested
        safe_profit = float(report.safe_profit_usd or 0)
        potential_loss = max(0.0, combined - 100.0) * safe_profit / 100.0
        if requested < 0 or requested > 100:
            raise ConflictException(
                f"Discount must be between 0% and 100% of protected profit. Requested: {requested:.2f}%."
            )
        if combined > 100 + 1e-9:
            remaining = max(0.0, 100.0 - existing)
            raise ConflictException(
                f"Discount cannot exceed {remaining:.2f}% for this purchase because {existing:.2f}% is already applied. "
                f"The combined {combined:.2f}% would exceed protected profit by {potential_loss:.6f} USD."
            )
        nominal = max(float(nominal_price_usd), 0.0)
        discount_amount = safe_profit * requested / 100.0
        if discount_amount > nominal + 1e-9:
            max_for_price = nominal / safe_profit * 100.0 if safe_profit > 0 else 0.0
            raise ConflictException(
                f"Discount cannot exceed {max_for_price:.2f}% for this product because its amount is lower than protected profit."
            )
        final = nominal - discount_amount
        return ProtectedCommercialPrice(
            nominal_price_usd=round(nominal, 6),
            requested_discount_percent=round(requested, 6),
            effective_discount_percent=round(requested, 6),
            maximum_allowed_discount_percent=round(max(0.0, 100.0 - existing), 6),
            safe_profit_usd=round(safe_profit, 9),
            discounted_profit_usd=round(discount_amount, 9),
            remaining_profit_usd=round(max(0.0, safe_profit * (100.0 - combined) / 100.0), 9),
            discount_amount_usd=round(discount_amount, 6),
            final_price_usd=round(final, 6),
            potential_loss_usd=round(potential_loss, 9),
            limiting_pricing_rule_id=report.limiting_pricing_rule_id,
            limiting_generation_module_id=report.limiting_generation_module_id,
            limiting_module_name=report.limiting_module_name,
            protected_discount_percent=100.0,
            calculated_maximum_safe_discount_percent=100.0,
            protection_limited=False,
        )


financial_protection_service = FinancialProtectionService()
