from __future__ import annotations

import json
import math
from dataclasses import dataclass
from decimal import Decimal
from statistics import median

from sqlalchemy.orm import Session

from app.common.enums import PricingOperationType, QualityMode, TryOnItemType
from app.common.exceptions import NotFoundException
from app.models.generation_module import GenerationModule
from app.models.system_setting import SystemSetting
from app.models.pricing_rule import PricingRule
from app.repositories.pricing_rule_repository import pricing_rule_repository
from app.repositories.system_setting_repository import system_setting_repository
from app.schemas.pricing import (
    CommercialPricePreviewResponse,
    CommercialSettingsResponse,
    CommercialSettingsUpdate,
    ExecutionBillingPolicy,
    ExecutionBillingPolicyUpdate,
    PricingRuleCreate,
    PricingRuleResponse,
    PricingRuleUpdate,
)
from app.schemas.provider_pricing import AppliedPricingRuleResponse
from app.services.ai_engine_settings_service import ai_engine_settings_service
from app.services.generation_module_execution_store_service import generation_module_execution_store_service
from app.services.provider_pricing_service import provider_pricing_service
from app.services.infrastructure_provider_service import infrastructure_provider_service
from app.services.token_financial_snapshot_service import token_financial_snapshot_service

TOKEN_VALUE_KEY = "commercial_token_value_usd"
OPERATIONAL_RESERVE_KEY = "commercial_operational_reserve_per_token_usd"
DEFAULT_TOKEN_VALUE_USD = 0.10
DEFAULT_CURRENCY = "USD"
BILLING_POLICY_KEY = "commercial_execution_billing_policy"
DEFAULT_EXECUTION_BILLING_POLICY = {
    "completed": {"charge_infrastructure": True, "apply_profit": True},
    "cancelled": {"charge_infrastructure": True, "apply_profit": False},
    "failed_workflow_or_user": {"charge_infrastructure": True, "apply_profit": False},
    "failed_platform_or_provider": {"charge_infrastructure": False, "apply_profit": False},
}


@dataclass(frozen=True, slots=True)
class PricingExecutionQuote:
    rule_id: int
    required_tokens: int
    estimated_gpu_seconds: int
    estimated_gpu_cost_cents: int
    desired_profit_usd: float = 0
    desired_profit_per_token_usd: float = 0
    technical_margin_seconds: int = 0


class PricingService:
    def _token_value(self, db: Session) -> float:
        setting = system_setting_repository.get_by_key(db, TOKEN_VALUE_KEY)
        value = setting.value_float if setting else DEFAULT_TOKEN_VALUE_USD
        return max(float(value or DEFAULT_TOKEN_VALUE_USD), 0.000001)

    def _operational_reserve(self, db: Session) -> float:
        setting = system_setting_repository.get_by_key(db, OPERATIONAL_RESERVE_KEY)
        return max(float(setting.value_float or 0) if setting else 0.0, 0.0)

    def _commercial_sale_value(self, db: Session) -> float:
        # Operational reserve is a commercial surcharge. It is deliberately
        # outside token_value_usd so generation-token math remains unchanged.
        return self._token_value(db) + self._operational_reserve(db)

    def _currency(self, db: Session) -> str:
        # The product is USD-only. Keep the response field for API compatibility
        # without exposing a fake configurable currency setting.
        return DEFAULT_CURRENCY

    def _billing_policy_setting(self, db: Session) -> SystemSetting:
        setting = system_setting_repository.get_by_key(db, BILLING_POLICY_KEY)
        if setting:
            return setting
        setting = SystemSetting(
            category="pricing",
            key=BILLING_POLICY_KEY,
            label="Execution billing policy",
            description="Controls infrastructure and profit charges by execution outcome.",
            value_type="json",
            value_json=json.dumps(DEFAULT_EXECUTION_BILLING_POLICY),
            default_value_json=json.dumps(DEFAULT_EXECUTION_BILLING_POLICY),
            is_public=False,
            is_editable=True,
            is_sensitive=False,
            requires_restart=False,
            sort_order=30,
        )
        db.add(setting)
        db.commit()
        db.refresh(setting)
        return setting

    def get_execution_billing_policy(self, db: Session) -> ExecutionBillingPolicy:
        setting = self._billing_policy_setting(db)
        try:
            raw = json.loads(setting.value_json or "{}")
        except (TypeError, ValueError):
            raw = {}
        merged = {
            key: {**value, **(raw.get(key) or {})}
            for key, value in DEFAULT_EXECUTION_BILLING_POLICY.items()
        }
        return ExecutionBillingPolicy.model_validate(merged)

    def update_execution_billing_policy(
        self, db: Session, data: ExecutionBillingPolicyUpdate
    ) -> ExecutionBillingPolicy:
        setting = self._billing_policy_setting(db)
        payload = data.model_dump()
        system_setting_repository.update(
            db, db_obj=setting, data={"value_json": json.dumps(payload)}
        )
        return ExecutionBillingPolicy.model_validate(payload)

    def price_for_tokens(self, db: Session, tokens: int) -> tuple[float, str]:
        amount = max(int(tokens), 0) * self._commercial_sale_value(db)
        return round(amount, 6), self._currency(db)


    def token_charge_for_infrastructure(
        self,
        db: Session,
        *,
        infrastructure_cost_usd: float,
        desired_profit_per_token_usd: float,
        apply_profit: bool = True,
    ) -> tuple[int, float, float, float]:
        """Return tokens, charged USD, configured profit and rounding surplus.

        Infrastructure capacity per token is token_value - profit_per_token.
        This removes circularity and guarantees the infrastructure cost is covered.
        """
        token_value = self._token_value(db)
        profit_per_token = max(float(desired_profit_per_token_usd or 0), 0.0) if apply_profit else 0.0
        infrastructure = max(float(infrastructure_cost_usd or 0), 0.0)
        if infrastructure <= 0:
            return 0, 0.0, 0.0, 0.0
        capacity = float(
            token_financial_snapshot_service.generation_infrastructure_capacity(
                token_value_usd=token_value,
                normal_profit_per_token_usd=profit_per_token,
            )
        )
        tokens = max(1, math.ceil(infrastructure / capacity))
        charged = tokens * token_value
        configured_profit = tokens * profit_per_token
        rounding_surplus = max(0.0, charged - infrastructure - configured_profit)
        return tokens, charged, configured_profit, rounding_surplus

    def get_commercial_settings(self, db: Session) -> CommercialSettingsResponse:
        return CommercialSettingsResponse(
            token_value_usd=self._token_value(db),
            operational_reserve_per_token_usd=self._operational_reserve(db),
            commercial_sale_value_per_token_usd=self._commercial_sale_value(db),
            currency=self._currency(db),
        )

    def update_commercial_settings(self, db: Session, data: CommercialSettingsUpdate) -> CommercialSettingsResponse:
        token_setting = system_setting_repository.get_by_key(db, TOKEN_VALUE_KEY)
        operational_setting = system_setting_repository.get_by_key(db, OPERATIONAL_RESERVE_KEY)
        if not token_setting:
            raise NotFoundException("Commercial settings are missing. Seed default system settings first.")
        if operational_setting is None:
            operational_setting = SystemSetting(
                category="pricing", key=OPERATIONAL_RESERVE_KEY,
                label="Operational reserve per token (USD)",
                description="Additional protected amount for company operating expenses.",
                value_type="float", value_float=0.0, default_value_float=0.0,
                is_public=False, is_editable=True, is_sensitive=False,
                requires_restart=False, sort_order=15,
            )
            db.add(operational_setting)
            db.flush()
        system_setting_repository.update(db, db_obj=token_setting, data={"value_float": float(data.token_value_usd)})
        if data.operational_reserve_per_token_usd is not None:
            system_setting_repository.update(db, db_obj=operational_setting, data={"value_float": float(data.operational_reserve_per_token_usd)})
        return self.get_commercial_settings(db)

    def preview(
        self,
        db: Session,
        *,
        average_execution_cost_usd: float,
        desired_profit_percent: float = 0,
        desired_profit_usd: float | None = None,
        desired_profit_per_token_usd: float = 0,
    ) -> CommercialPricePreviewResponse:
        cost = max(float(average_execution_cost_usd), 0)
        tokens, final_price, configured_profit, _rounding = self.token_charge_for_infrastructure(
            db, infrastructure_cost_usd=cost,
            desired_profit_per_token_usd=desired_profit_per_token_usd,
            apply_profit=True,
        )
        effective_margin = ((final_price - cost) / cost * 100) if cost > 0 else 0.0
        return CommercialPricePreviewResponse(
            average_execution_cost_usd=round(cost, 9),
            desired_profit_percent=round(float(desired_profit_percent or 0), 6),
            desired_profit_usd=round(configured_profit, 9),
            desired_profit_per_token_usd=round(float(desired_profit_per_token_usd or 0), 9),
            token_value_usd=round(self._token_value(db), 9),
            currency=self._currency(db),
            final_price_usd=round(final_price, 9),
            required_tokens=tokens,
            effective_margin_percent=round(effective_margin, 6),
        )

    def _to_response(self, db: Session, rule: PricingRule) -> PricingRuleResponse:
        average_cost = float(rule.estimated_gpu_cost_cents or 0) / 100
        legacy_percent = float(rule.margin_percent or 0)
        desired_profit_usd = float(rule.desired_profit_usd or 0)
        desired_profit_per_token_usd = float(rule.desired_profit_per_token_usd or 0)
        preview = self.preview(
            db,
            average_execution_cost_usd=average_cost,
            desired_profit_percent=legacy_percent,
            desired_profit_usd=desired_profit_usd,
            desired_profit_per_token_usd=desired_profit_per_token_usd,
        )
        return PricingRuleResponse(
            id=rule.id,
            title=rule.title,
            operation_type=rule.operation_type,
            item_type=rule.item_type,
            quality_mode=rule.quality_mode,
            generation_module_id=rule.generation_module_id,
            desired_profit_usd=desired_profit_usd,
            desired_profit_per_token_usd=desired_profit_per_token_usd,
            initial_estimated_duration_seconds=max(int(rule.initial_estimated_duration_seconds or 30), 1),
            technical_margin_seconds=max(int(rule.technical_margin_seconds or 0), 0),
            average_execution_cost_usd=average_cost,
            desired_profit_percent=legacy_percent,
            final_price_usd=preview.final_price_usd,
            required_tokens=preview.required_tokens,
            effective_margin_percent=preview.effective_margin_percent,
            token_value_usd=preview.token_value_usd,
            currency=preview.currency,
            is_active=rule.is_active,
            created_at=rule.created_at,
            updated_at=rule.updated_at,
        )

    def _get_active_tryon_rule(self, db: Session, *, item_type: TryOnItemType, quality_mode: QualityMode) -> PricingRule:
        rule = pricing_rule_repository.get_active_rule(
            db,
            operation_type=PricingOperationType.TRYON.value,
            item_type=item_type.value,
            quality_mode=quality_mode.value,
        )
        if not rule:
            raise NotFoundException("No active pricing rule found for this operation.")
        return rule

    def get_tryon_price(self, db: Session, *, item_type: TryOnItemType, quality_mode: QualityMode) -> PricingRuleResponse:
        return self._to_response(db, self._get_active_tryon_rule(db, item_type=item_type, quality_mode=quality_mode))

    def get_tryon_execution_quote(self, db: Session, *, item_type: TryOnItemType, quality_mode: QualityMode) -> PricingExecutionQuote:
        rule = self._get_active_tryon_rule(db, item_type=item_type, quality_mode=quality_mode)
        response = self._to_response(db, rule)
        return PricingExecutionQuote(
            rule_id=rule.id,
            required_tokens=response.required_tokens,
            estimated_gpu_seconds=max(int(rule.initial_estimated_duration_seconds or rule.estimated_gpu_seconds or 0), 0),
            estimated_gpu_cost_cents=max(int(rule.estimated_gpu_cost_cents or 0), 0),
            desired_profit_usd=float(rule.desired_profit_usd or 0),
            desired_profit_per_token_usd=float(rule.desired_profit_per_token_usd or 0),
            technical_margin_seconds=max(int(rule.technical_margin_seconds or 0), 0),
        )

    def list_rules(self, db: Session) -> list[PricingRuleResponse]:
        return [self._to_response(db, rule) for rule in pricing_rule_repository.list_all(db)]

    def create_rule(self, db: Session, data: PricingRuleCreate) -> PricingRuleResponse:
        legacy_cost = float(data.average_execution_cost_usd or 0)
        legacy_percent = float(data.desired_profit_percent or 0)
        preview = self.preview(
            db,
            average_execution_cost_usd=legacy_cost,
            desired_profit_percent=legacy_percent,
            desired_profit_usd=data.desired_profit_usd,
            desired_profit_per_token_usd=data.desired_profit_per_token_usd,
        )
        rule = PricingRule(
            title=data.title.strip(),
            operation_type=data.operation_type.value,
            item_type=data.item_type.value,
            quality_mode=data.quality_mode.value,
            generation_module_id=data.generation_module_id,
            tokens_cost=preview.required_tokens,
            estimated_gpu_seconds=data.initial_estimated_duration_seconds,
            estimated_gpu_cost_cents=round(legacy_cost * 100),
            margin_percent=round(legacy_percent),
            desired_profit_usd=Decimal(str(data.desired_profit_usd or 0)),
            desired_profit_per_token_usd=Decimal(str(data.desired_profit_per_token_usd)),
            initial_estimated_duration_seconds=data.initial_estimated_duration_seconds,
            technical_margin_seconds=data.technical_margin_seconds,
            is_active=data.is_active,
        )
        db.add(rule)
        db.flush()
        from app.services.financial_protection_service import financial_protection_service
        report = financial_protection_service.report(db)
        financial_protection_service.assert_report_safe(report, action="create pricing rule")
        db.commit()
        db.refresh(rule)
        return self._to_response(db, rule)

    def update_rule(self, db: Session, rule_id: int, data: PricingRuleUpdate) -> PricingRuleResponse:
        rule = pricing_rule_repository.get_by_id(db, rule_id)
        if not rule:
            raise NotFoundException("Pricing rule not found.")
        update_data = {}
        for field in ("desired_profit_usd", "desired_profit_per_token_usd", "initial_estimated_duration_seconds", "technical_margin_seconds", "is_active"):
            value = getattr(data, field)
            if value is not None:
                update_data[field] = Decimal(str(value)) if field in {"desired_profit_usd", "desired_profit_per_token_usd"} else value
        if data.title is not None:
            update_data["title"] = data.title.strip()
        if "generation_module_id" in data.model_fields_set:
            update_data["generation_module_id"] = data.generation_module_id
        if data.average_execution_cost_usd is not None:
            update_data["estimated_gpu_cost_cents"] = round(data.average_execution_cost_usd * 100)
        if data.desired_profit_percent is not None:
            update_data["margin_percent"] = round(data.desired_profit_percent)
        if data.initial_estimated_duration_seconds is not None:
            update_data["estimated_gpu_seconds"] = data.initial_estimated_duration_seconds
        # Validate the merged financial rule BEFORE the repository commits it.
        # This keeps the existing token economics authoritative and prevents an
        # invalid profit-per-token from being persisted by an UPDATE.
        merged_profit = float(update_data.get("desired_profit_per_token_usd", rule.desired_profit_per_token_usd or 0))
        token_financial_snapshot_service.generation_infrastructure_capacity(
            token_value_usd=self._token_value(db),
            normal_profit_per_token_usd=merged_profit,
        )
        from app.services.financial_protection_service import financial_protection_service
        financial_protection_service.assert_rule_change(
            db, rule.id, update_data, action="update pricing rule"
        )
        rule = pricing_rule_repository.update(db, db_obj=rule, data=update_data)
        return self._to_response(db, rule)

    def delete_rule(self, db: Session, rule_id: int) -> None:
        rule = pricing_rule_repository.get_by_id(db, rule_id)
        if not rule:
            raise NotFoundException("Pricing rule not found.")
        if rule.generation_module_id is not None:
            module = db.get(GenerationModule, rule.generation_module_id)
            if module is not None:
                module.is_active = False
                db.add(module)
        db.delete(rule)
        db.commit()

    @staticmethod
    def _execution_duration_seconds(row) -> float | None:
        """Return the best completed-runtime duration available in an execution snapshot."""
        provider_metrics = row.provider_metrics or {}
        billing = row.billing_breakdown or {}
        candidates_seconds = (
            provider_metrics.get("real_provider_seconds"),
            billing.get("real_provider_seconds"),
        )
        for value in candidates_seconds:
            try:
                seconds = float(value)
            except (TypeError, ValueError):
                continue
            if seconds > 0:
                return seconds

        candidates_ms = (
            row.real_provider_duration_ms,
            provider_metrics.get("execution_time_ms"),
            row.duration_ms,
        )
        for value in candidates_ms:
            try:
                milliseconds = float(value)
            except (TypeError, ValueError):
                continue
            if milliseconds > 0:
                return milliseconds / 1000.0
        return None

    def _historical_duration(
        self, module_id: int, fallback: int
    ) -> tuple[float, str, int, str, str | None]:
        rows, _ = generation_module_execution_store_service.list(
            module_id=module_id,
            status="completed",
            skip=0,
            limit=5,
        )
        samples: list[tuple[float, object]] = []
        for row in rows:
            if str(getattr(row, "accounting_mode", "commercial") or "commercial") != "commercial":
                continue
            duration = self._execution_duration_seconds(row)
            if duration is not None:
                samples.append((duration, row))

        if not samples:
            return float(fallback), "initial", 0, "low", None

        # Protect the estimate from an isolated extreme execution without requiring
        # five samples before learning. One valid completed generation is enough.
        durations = [item[0] for item in samples]
        if len(durations) >= 4:
            center = median(durations)
            lower = max(center * 0.5, 0.001)
            upper = center * 2.0
            filtered = [item for item in samples if lower <= item[0] <= upper]
            if filtered:
                samples = filtered

        # Use the five most recent completed commercial executions for this
        # module, preserving the existing outlier protection and the highest
        # valid historical duration as the conservative estimate.
        count = len(samples)
        estimate = max(duration for duration, _row in samples)
        confidence = "high" if count >= 5 else "medium" if count >= 2 else "low"
        latest = samples[0][1]
        latest_at = latest.finished_at or latest.updated_at or latest.created_at
        return round(estimate, 3), "historical_max", count, confidence, latest_at.isoformat() if latest_at else None

    def get_applied_rule_for_module(self, db: Session, module_id: int) -> AppliedPricingRuleResponse | None:
        return next((item for item in self.list_applied_rules(db) if item.generation_module_id == module_id), None)

    def list_applied_rules(self, db: Session) -> list[AppliedPricingRuleResponse]:
        settings = ai_engine_settings_service.get(db)
        token_value = self._token_value(db)
        responses: list[AppliedPricingRuleResponse] = []
        for rule in pricing_rule_repository.list_all(db):
            if rule.generation_module_id is None:
                continue
            module = db.get(GenerationModule, rule.generation_module_id)
            if module is None:
                continue
            provider = str(module.default_execution_engine or "").lower()
            if provider == "modal":
                # Resolve the GPU from the runtime selected by this generation module.
                # Pricing formulas remain unchanged; only the GPU source moves from
                # global Modal settings to the selected Runtime Builder profile.
                gpu_key = None
                try:
                    from app.services.generation_execution_target_service import generation_execution_target_service
                    targets = generation_execution_target_service.list_targets(db).get("modal", [])
                    selected_target = next((item for item in targets if item.get("value") == module.endpoint), None)
                    if selected_target and selected_target.get("runtime_config_id"):
                        from app.models.runtime_builder_config import RuntimeBuilderConfig
                        runtime_cfg = db.get(RuntimeBuilderConfig, int(selected_target["runtime_config_id"]))
                        gpu_key = str(getattr(runtime_cfg, "gpu", "") or "").strip() or None
                except Exception:
                    gpu_key = None
                # Compatibility fallback for modules/runtimes created before per-runtime GPU.
                gpu_key = gpu_key or settings.modal_gpu
                scaledown = settings.modal_scaledown_window_seconds
            elif provider == "local_docker":
                local_cfg = infrastructure_provider_service.get_local_docker(db)
                gpu_key = str(local_cfg.gpu or "").strip() or None
                scaledown = 0
            elif provider == "owner_local":
                owner_cfg = infrastructure_provider_service.get_owner_local(db)
                gpu_key = str(owner_cfg.gpu or "").strip() or None
                scaledown = 0
            else:
                gpu_key = None
                scaledown = 0
            gpu_cost = provider_pricing_service.get_cost(db, provider=provider, gpu_key=gpu_key)
            duration, source, sample_count, confidence, estimate_updated_at = self._historical_duration(
                module.id, int(rule.initial_estimated_duration_seconds or 30)
            )
            billable = duration + scaledown + int(rule.technical_margin_seconds or 0)
            infra = billable * gpu_cost if gpu_cost is not None else None
            profit_per_token = float(rule.desired_profit_per_token_usd or 0)
            if infra is not None:
                try:
                    tokens, total, configured_profit, _rounding = self.token_charge_for_infrastructure(
                        db, infrastructure_cost_usd=infra,
                        desired_profit_per_token_usd=profit_per_token, apply_profit=True,
                    )
                except Exception as exc:
                    tokens = None; total = None; configured_profit = None
                    calculation_error = str(exc) or "Pricing rule cannot be calculated."
                else:
                    calculation_error = None
            else:
                tokens = None; total = None; configured_profit = None
                calculation_error = None
            warnings = []
            if calculation_error:
                warnings.append(f"Regla financiera inválida: {calculation_error}")
            if gpu_key is None:
                warnings.append("GPU selection is not yet configured for this provider.")
            if gpu_cost is None:
                warnings.append("GPU cost per second is missing.")
            responses.append(AppliedPricingRuleResponse(
                rule_id=rule.id,
                rule_title=rule.title,
                generation_module_id=module.id,
                module_key=module.key,
                module_name=module.name,
                provider=provider,
                gpu_key=gpu_key,
                gpu_cost_usd_per_second=gpu_cost,
                estimated_duration_seconds=duration,
                estimate_source=source,
                historical_samples_used=sample_count,
                estimate_confidence=confidence,
                estimate_updated_at=estimate_updated_at,
                scaledown_seconds=scaledown,
                technical_margin_seconds=int(rule.technical_margin_seconds or 0),
                estimated_billable_seconds=round(billable, 3),
                estimated_infrastructure_cost_usd=round(infra, 9) if infra is not None else None,
                desired_profit_usd=float(configured_profit or 0),
                desired_profit_per_token_usd=profit_per_token,
                estimated_final_price_usd=round(total, 9) if total is not None else None,
                token_value_usd=token_value,
                estimated_tokens=tokens,
                configured=not warnings,
                warnings=warnings,
            ))
        return responses

    def reprice_catalog(self, db: Session) -> dict[str, int | float | str]:
        from app.repositories.subscription_plan_repository import subscription_plan_repository
        from app.repositories.token_package_repository import token_package_repository
        plans = subscription_plan_repository.list_all_filtered(db, skip=0, limit=10000)
        packages = token_package_repository.list_all(db)
        currency = self._currency(db)
        from app.services.financial_protection_service import financial_protection_service
        for plan in plans:
            amount, _ = self.price_for_tokens(db, plan.tokens_per_period)
            try:
                metadata = json.loads(plan.metadata_json or "{}")
            except (TypeError, ValueError):
                metadata = {}
            protected = financial_protection_service.protected_price(
                db, nominal_price_usd=amount,
                requested_discount_percent=float(metadata.get("requested_discount_percent") or 0), tokens_amount=plan.tokens_per_period,
            )
            metadata["effective_discount_percent"] = protected.effective_discount_percent
            metadata["financial_protection_snapshot"] = protected.model_dump()
            plan.price_amount = Decimal(str(protected.final_price_usd))
            plan.currency = currency
            plan.metadata_json = json.dumps(metadata, ensure_ascii=False)
            db.add(plan)
        for package in packages:
            amount, _ = self.price_for_tokens(db, package.tokens_amount)
            protected = financial_protection_service.protected_price(
                db, nominal_price_usd=amount,
                requested_discount_percent=float(package.requested_discount_percent or 0), tokens_amount=package.tokens_amount,
            )
            package.nominal_price_cents = int(round(protected.nominal_price_usd * 100))
            package.price_cents = int(round(protected.final_price_usd * 100))
            package.effective_discount_percent = protected.effective_discount_percent
            package.currency = currency.lower()
            db.add(package)
        db.commit()
        return {"plans_updated": len(plans), "packages_updated": len(packages), "currency": currency, "token_value_usd": self._token_value(db)}


pricing_service = PricingService()
