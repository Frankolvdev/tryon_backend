from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.common.exceptions import ConflictException
from app.models.generation_module import GenerationModule
from app.models.system_setting import SystemSetting
from app.repositories.pricing_rule_repository import pricing_rule_repository
from app.repositories.system_setting_repository import system_setting_repository
from app.schemas.financial_protection import (
    FinancialProtectionReport,
    FinancialProtectionRuleDiagnostic,
    FinancialProtectionSettings,
    FinancialProtectionSettingsUpdate,
    ProtectedCommercialPrice,
)
from app.services.ai_engine_settings_service import ai_engine_settings_service
from app.services.provider_pricing_service import provider_pricing_service

PROTECTION_KEY = "commercial_financial_protection"
DEFAULT_PROTECTION = {
    "protected_discount_percent": 0.0,
    "duration_safety_buffer_percent": 10.0,
}


class FinancialProtectionService:
    def _setting(self, db: Session) -> SystemSetting:
        row = system_setting_repository.get_by_key(db, PROTECTION_KEY)
        if row:
            return row
        row = SystemSetting(
            category="pricing",
            key=PROTECTION_KEY,
            label="Financial discount protection",
            description="Global protected discount and conservative duration buffer.",
            value_type="json",
            value_json=json.dumps(DEFAULT_PROTECTION),
            default_value_json=json.dumps(DEFAULT_PROTECTION),
            is_public=False,
            is_editable=True,
            is_sensitive=False,
            requires_restart=False,
            sort_order=31,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def get_settings(self, db: Session) -> FinancialProtectionSettings:
        row = self._setting(db)
        try:
            raw = json.loads(row.value_json or "{}")
        except (TypeError, ValueError):
            raw = {}
        return FinancialProtectionSettings.model_validate({**DEFAULT_PROTECTION, **raw})

    def _provider_context(self, db: Session, provider: str) -> tuple[str | None, int]:
        settings = ai_engine_settings_service.get(db)
        provider = provider.strip().lower()
        if provider == "modal":
            return settings.modal_gpu, int(settings.modal_scaledown_window_seconds or 0)
        # RunPod and Beam are deliberately reported as incomplete until their selected GPU
        # and idle window are exposed through the same provider contract.
        return None, 0

    def report(
        self,
        db: Session,
        *,
        settings_override: FinancialProtectionSettings | None = None,
        rule_overrides: dict[int, dict[str, Any]] | None = None,
        gpu_cost_overrides: dict[tuple[str, str], float | None] | None = None,
    ) -> FinancialProtectionReport:
        settings = settings_override or self.get_settings(db)
        rule_overrides = rule_overrides or {}
        gpu_cost_overrides = gpu_cost_overrides or {}
        diagnostics: list[FinancialProtectionRuleDiagnostic] = []
        warnings: list[str] = []

        for rule in pricing_rule_repository.list_all(db):
            override = rule_overrides.get(rule.id, {})
            active = bool(override.get("is_active", rule.is_active))
            module_id = override.get("generation_module_id", rule.generation_module_id)
            if not active or module_id is None:
                continue
            module = db.get(GenerationModule, module_id)
            if module is None or not module.is_active:
                continue
            provider = str(module.default_execution_engine or "").strip().lower()
            gpu_key, scaledown = self._provider_context(db, provider)
            duration = max(float(override.get("initial_estimated_duration_seconds", rule.initial_estimated_duration_seconds or 0)), 0)
            margin = max(float(override.get("technical_margin_seconds", rule.technical_margin_seconds or 0)), 0)
            profit = max(float(override.get("desired_profit_usd", rule.desired_profit_usd or 0)), 0)
            protected_duration = duration * (1 + settings.duration_safety_buffer_percent / 100)
            billable = protected_duration + scaledown + margin
            local_warnings: list[str] = []
            if not provider:
                local_warnings.append("Infrastructure provider is missing.")
            if not gpu_key:
                local_warnings.append("Selected GPU is missing for this provider.")
            key = (provider, gpu_key or "")
            if key in gpu_cost_overrides:
                gpu_cost = gpu_cost_overrides[key]
            else:
                gpu_cost = provider_pricing_service.get_cost(db, provider=provider, gpu_key=gpu_key)
            if gpu_cost is None or gpu_cost <= 0:
                local_warnings.append("Active GPU cost per second is missing or invalid.")
            infra = billable * gpu_cost if gpu_cost is not None and gpu_cost > 0 else None
            normal = infra + profit if infra is not None else None
            safe = (profit / normal * 100) if normal and normal > 0 else None
            diagnostics.append(FinancialProtectionRuleDiagnostic(
                pricing_rule_id=rule.id,
                generation_module_id=module.id,
                module_key=module.key,
                module_name=module.name,
                provider=provider,
                gpu_key=gpu_key,
                protected_duration_seconds=round(protected_duration, 3),
                billable_seconds=round(billable, 3),
                gpu_cost_usd_per_second=round(gpu_cost, 12) if gpu_cost is not None else None,
                infrastructure_cost_usd=round(infra, 9) if infra is not None else None,
                desired_profit_usd=round(profit, 9),
                normal_price_usd=round(normal, 9) if normal is not None else None,
                maximum_safe_discount_percent=round(safe, 6) if safe is not None else None,
                configured=not local_warnings,
                warnings=local_warnings,
            ))

        configured = [d for d in diagnostics if d.configured and d.maximum_safe_discount_percent is not None]
        incomplete = [d for d in diagnostics if not d.configured]
        if incomplete:
            warnings.append(f"{len(incomplete)} active pricing application(s) are incomplete.")
        limiting = min(configured, key=lambda item: item.maximum_safe_discount_percent or 0) if configured else None
        calculated = limiting.maximum_safe_discount_percent if limiting else None
        protected = settings.protected_discount_percent
        headroom = calculated - protected if calculated is not None else None
        if not diagnostics:
            status = "not_configured"
            warnings.append("No active applied pricing rules are available.")
        elif incomplete:
            status = "incomplete"
        elif calculated is None:
            status = "not_configured"
        elif headroom is not None and headroom < 0:
            status = "blocked"
        elif headroom is not None and headroom < 1:
            status = "high_risk"
        elif headroom is not None and headroom < 5:
            status = "caution"
        else:
            status = "protected"
        return FinancialProtectionReport(
            protected_discount_percent=round(protected, 6),
            duration_safety_buffer_percent=round(settings.duration_safety_buffer_percent, 6),
            calculated_maximum_safe_discount_percent=calculated,
            available_headroom_percentage_points=round(headroom, 6) if headroom is not None else None,
            status=status,
            limiting_pricing_rule_id=limiting.pricing_rule_id if limiting else None,
            limiting_generation_module_id=limiting.generation_module_id if limiting else None,
            limiting_module_key=limiting.module_key if limiting else None,
            limiting_module_name=limiting.module_name if limiting else None,
            limiting_provider=limiting.provider if limiting else None,
            limiting_gpu_key=limiting.gpu_key if limiting else None,
            diagnostics=diagnostics,
            warnings=warnings,
        )

    def assert_report_safe(self, report: FinancialProtectionReport, *, action: str) -> None:
        if report.status == "incomplete" and report.protected_discount_percent > 0:
            raise ConflictException(
                f"Cannot {action}: financial protection cannot be verified because an active pricing application is incomplete."
            )
        if report.calculated_maximum_safe_discount_percent is None:
            if report.protected_discount_percent > 0:
                raise ConflictException(f"Cannot {action}: no safe global discount can be calculated.")
            return
        if report.calculated_maximum_safe_discount_percent + 1e-9 < report.protected_discount_percent:
            deficit = report.protected_discount_percent - report.calculated_maximum_safe_discount_percent
            raise ConflictException(
                f"Cannot {action}: the change would reduce the safe discount to "
                f"{report.calculated_maximum_safe_discount_percent:.2f}% while the protected commitment is "
                f"{report.protected_discount_percent:.2f}% (deficit {deficit:.2f} percentage points). "
                f"Limiting module: {report.limiting_module_name or 'unknown'}."
            )

    def update_settings(self, db: Session, data: FinancialProtectionSettingsUpdate) -> FinancialProtectionReport:
        candidate = FinancialProtectionSettings.model_validate(data.model_dump())
        report = self.report(db, settings_override=candidate)
        self.assert_report_safe(report, action="update financial protection")
        row = self._setting(db)
        system_setting_repository.update(db, db_obj=row, data={"value_json": json.dumps(candidate.model_dump())})
        return self.report(db)

    def assert_rule_change(self, db: Session, rule_id: int, values: dict[str, Any], *, action: str) -> None:
        report = self.report(db, rule_overrides={rule_id: values})
        self.assert_report_safe(report, action=action)

    def assert_gpu_price_change(self, db: Session, *, provider: str, gpu_key: str, cost: float | None, action: str) -> None:
        report = self.report(db, gpu_cost_overrides={(provider.strip().lower(), gpu_key.strip()): cost})
        self.assert_report_safe(report, action=action)

    def protected_price(self, db: Session, *, nominal_price_usd: float, requested_discount_percent: float) -> ProtectedCommercialPrice:
        report = self.report(db)
        self.assert_report_safe(report, action="price commercial catalog")
        requested = max(min(float(requested_discount_percent), 100), 0)
        protected_limit = max(float(report.protected_discount_percent), 0)
        if requested > protected_limit + 1e-9:
            raise ConflictException(
                f"Requested discount {requested:.2f}% exceeds the globally protected maximum {protected_limit:.2f}%."
            )
        effective = requested
        nominal = max(float(nominal_price_usd), 0)
        discount = nominal * effective / 100
        final = nominal - discount
        return ProtectedCommercialPrice(
            nominal_price_usd=round(nominal, 6),
            requested_discount_percent=round(requested, 6),
            effective_discount_percent=round(effective, 6),
            discount_amount_usd=round(discount, 6),
            final_price_usd=round(final, 6),
            protected_discount_percent=round(protected_limit, 6),
            calculated_maximum_safe_discount_percent=report.calculated_maximum_safe_discount_percent,
            protection_limited=False,
        )


financial_protection_service = FinancialProtectionService()
