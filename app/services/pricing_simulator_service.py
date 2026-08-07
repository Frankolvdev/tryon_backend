from __future__ import annotations

import math
from sqlalchemy.orm import Session

from app.common.exceptions import ConflictException, NotFoundException
from app.schemas.pricing_simulator import (
    PricingSimulatorRequest, PricingSimulatorResponse,
    PricingSimulatorScenarioResponse, PricingSimulatorRecommendation,
)
from app.services.pricing_service import pricing_service
from app.services.token_financial_snapshot_service import token_financial_snapshot_service


class PricingSimulatorService:
    @staticmethod
    def _scenario(*, token_value: float, profit_per_token: float, operational_per_token: float, infra: float, discount: float, label: str):
        capacity = float(
            token_financial_snapshot_service.generation_infrastructure_capacity(
                token_value_usd=token_value,
                normal_profit_per_token_usd=profit_per_token,
            )
        )
        tokens = max(1, math.ceil(infra / capacity)) if infra > 0 else 0
        normal_profit = tokens * profit_per_token
        discount_given = normal_profit * (discount / 100.0)
        profit_after = normal_profit - discount_given
        operational_total = tokens * max(float(operational_per_token or 0), 0.0)
        customer_value = tokens * (token_value + max(float(operational_per_token or 0), 0.0)) - discount_given
        rounding = max(0.0, customer_value - infra - operational_total - profit_after)
        return PricingSimulatorScenarioResponse(
            label=label, discount_percent=round(discount, 4), tokens=tokens,
            customer_value_usd=round(customer_value, 9), infrastructure_cost_usd=round(infra, 9),
            operational_reserve_usd=round(operational_total, 9),
            normal_profit_usd=round(normal_profit, 9), discount_given_usd=round(discount_given, 9),
            profit_after_discount_usd=round(profit_after, 9), rounding_surplus_usd=round(rounding, 9),
            company_total_usd=round(profit_after + rounding, 9),
        )

    def simulate(self, db: Session, data: PricingSimulatorRequest) -> PricingSimulatorResponse:
        applied = pricing_service.get_applied_rule_for_module(db, data.generation_module_id)
        if applied is None:
            raise NotFoundException("No active pricing rule is configured for this generation module.")
        if applied.gpu_cost_usd_per_second is None:
            raise ConflictException("GPU cost per second is missing for this module.")
        rule = next((r for r in pricing_service.list_rules(db) if r.id == applied.rule_id), None)
        if rule is None:
            raise NotFoundException("Pricing rule not found.")

        if data.duration_mode == "manual":
            duration = float(data.manual_duration_seconds or 0)
            source = "manual"
            samples = 0
            confidence = "manual"
        elif data.duration_mode == "initial":
            duration = float(rule.initial_estimated_duration_seconds)
            source = "initial"
            samples = 0
            confidence = "initial"
        else:
            duration = float(applied.estimated_duration_seconds)
            source = str(applied.estimate_source)
            samples = int(getattr(applied, "historical_samples_used", 0) or 0)
            confidence = str(getattr(applied, "estimate_confidence", "initial") or "initial")

        billable = duration + int(applied.scaledown_seconds or 0) + int(applied.technical_margin_seconds or 0)
        infra = billable * float(applied.gpu_cost_usd_per_second)
        current_token = float(applied.token_value_usd)
        current_operational = float(pricing_service._operational_reserve(db))
        current_profit = float(applied.desired_profit_per_token_usd)
        token_value = float(data.token_value_usd if data.token_value_usd is not None else current_token)
        profit = float(data.desired_profit_per_token_usd if data.desired_profit_per_token_usd is not None else current_profit)
        if profit >= token_value:
            raise ConflictException(f"Desired profit per token must be lower than token value ({token_value:.9f} USD).")

        requested = data.scenarios or [
            {"label": "Sin descuento", "discount_percent": 0},
            {"label": "Descuento habitual", "discount_percent": data.worst_discount_percent},
        ]
        scenarios = [self._scenario(token_value=token_value, profit_per_token=profit, operational_per_token=current_operational, infra=infra,
                                   discount=float(s.discount_percent if hasattr(s, 'discount_percent') else s['discount_percent']),
                                   label=str(s.label if hasattr(s, 'label') else s['label'])) for s in requested]

        recommendations = []
        if data.target_profit_usd is not None:
            min_tokens = data.target_tokens_min or 1
            max_tokens = data.target_tokens_max or 30
            candidates = []
            # Keep token value close to the supplied/current value while exploring practical cent increments.
            base = token_value
            values = sorted({round(max(0.01, base + step * 0.01), 4) for step in range(-10, 21)})
            for tv in values:
                for gap_mills in range(1, 101):
                    gap = gap_mills / 1000.0
                    pp = tv - gap
                    if pp <= 0 or pp >= tv:
                        continue
                    scenario = self._scenario(token_value=tv, profit_per_token=pp, operational_per_token=current_operational, infra=infra,
                                              discount=data.worst_discount_percent, label="Objetivo")
                    if not (min_tokens <= scenario.tokens <= max_tokens):
                        continue
                    distance = abs(scenario.company_total_usd - data.target_profit_usd)
                    candidates.append((distance, abs(tv-base), scenario, tv, pp))
            for distance, _token_distance, scenario, candidate_token_value, pp in sorted(candidates, key=lambda x: (x[0], x[1], x[2].tokens))[:8]:
                recommendations.append(PricingSimulatorRecommendation(
                    token_value_usd=round(candidate_token_value, 6),
                    desired_profit_per_token_usd=round(pp, 6), tokens=scenario.tokens,
                    worst_discount_percent=round(data.worst_discount_percent, 4),
                    estimated_company_profit_usd=scenario.company_total_usd,
                    estimated_customer_value_usd=scenario.customer_value_usd,
                    distance_from_target_usd=round(distance, 9),
                ))

        warnings = []
        if samples == 0 and data.duration_mode == "historical":
            warnings.append("No completed history exists yet; the initial configured duration is being used.")
        return PricingSimulatorResponse(
            generation_module_id=applied.generation_module_id, module_key=applied.module_key,
            module_name=applied.module_name, pricing_rule_id=applied.rule_id,
            pricing_rule_title=applied.rule_title, provider=applied.provider, gpu_key=applied.gpu_key,
            gpu_cost_usd_per_second=float(applied.gpu_cost_usd_per_second), duration_seconds=round(duration, 3),
            duration_source=source, historical_samples_used=samples, estimate_confidence=confidence,
            scaledown_seconds=int(applied.scaledown_seconds or 0), technical_margin_seconds=int(applied.technical_margin_seconds or 0),
            billable_seconds=round(billable, 3), infrastructure_cost_usd=round(infra, 9),
            current_token_value_usd=round(current_token, 9),
            current_operational_reserve_per_token_usd=round(current_operational, 9),
            current_profit_per_token_usd=round(current_profit, 9),
            simulated_token_value_usd=round(token_value, 9),
            simulated_operational_reserve_per_token_usd=round(current_operational, 9),
            simulated_profit_per_token_usd=round(profit, 9),
            scenarios=scenarios, recommendations=recommendations, warnings=warnings,
        )


pricing_simulator_service = PricingSimulatorService()
