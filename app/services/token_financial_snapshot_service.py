from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping

from app.common.exceptions import ConflictException

D = Decimal
EPSILON = D("0.000000001")
SNAPSHOT_VERSION = 3
ECONOMICS_SCHEMA = "explicit_components_v3"


@dataclass(frozen=True, slots=True)
class TokenFinancialComponents:
    paid_value_per_token: D
    token_value_per_token: D
    normal_profit_per_token: D
    effective_profit_per_token: D
    infrastructure_capacity_per_token: D
    operational_reserve_per_token: D
    profit_discount_percent: D
    snapshot_source: str
    metadata: dict[str, Any]


class TokenFinancialSnapshotService:
    """Single source of truth for the economic components frozen in token lots.

    A token lot stores independent components. Consumers must read those frozen
    components instead of reconstructing infrastructure as ``paid - profit``.
    The explicit operational component is zero today; MegaZIP 4 can populate it
    without changing generation-token math or historical lots.
    """

    @staticmethod
    def decimal(value: object, default: D = D("0")) -> D:
        try:
            return D(str(value))
        except (TypeError, ValueError, ArithmeticError):
            return default

    def generation_infrastructure_capacity(
        self,
        *,
        token_value_usd: object,
        normal_profit_per_token_usd: object,
    ) -> D:
        token_value = max(self.decimal(token_value_usd), D("0"))
        normal_profit = max(self.decimal(normal_profit_per_token_usd), D("0"))
        if normal_profit >= token_value:
            raise ConflictException(
                f"Desired profit per token must be lower than token value ({float(token_value):.9f} USD)."
            )
        capacity = token_value - normal_profit
        if capacity <= 0:
            raise ConflictException("The pricing rule does not leave a positive AI infrastructure reserve per token.")
        return capacity

    def build_commercial_terms(
        self,
        *,
        token_value_usd: object,
        normal_profit_per_token_usd: object,
        profit_discount_percent: object = 0,
        operational_reserve_per_token_usd: object = 0,
        **extra: Any,
    ) -> dict[str, Any]:
        token_value = max(self.decimal(token_value_usd), D("0"))
        normal_profit = max(self.decimal(normal_profit_per_token_usd), D("0"))
        discount = min(max(self.decimal(profit_discount_percent), D("0")), D("100"))
        infrastructure = self.generation_infrastructure_capacity(
            token_value_usd=token_value,
            normal_profit_per_token_usd=normal_profit,
        )
        operational = max(self.decimal(operational_reserve_per_token_usd), D("0"))
        effective_profit = normal_profit * (D("1") - discount / D("100"))
        payload: dict[str, Any] = {
            "financial_snapshot_version": SNAPSHOT_VERSION,
            "financial_economics_schema": ECONOMICS_SCHEMA,
            "token_value_usd": str(token_value),
            "normal_profit_per_token_usd": str(normal_profit),
            "profit_discount_percent": str(discount),
            "effective_profit_per_token_usd": str(effective_profit),
            "infrastructure_capacity_per_token_usd": str(infrastructure),
            "operational_reserve_per_token_usd": str(operational),
            "infrastructure_reserve_source": "pricing_rule_fixed",
            "operational_reserve_source": "explicit_snapshot",
        }
        payload.update(extra)
        return payload

    def normalize_new_lot_snapshot(
        self,
        snapshot: Mapping[str, Any] | None,
        *,
        paid_value_per_token: object,
    ) -> dict[str, Any]:
        data = dict(snapshot or {})
        paid = max(self.decimal(paid_value_per_token), D("0"))
        promotional = bool(data.get("promotional_credit_funded"))

        normal_profit = max(self.decimal(data.get("normal_profit_per_token_usd")), D("0"))
        discount = min(max(self.decimal(data.get("profit_discount_percent")), D("0")), D("100"))
        requested_effective = self.decimal(
            data.get("effective_profit_per_token_usd"),
            normal_profit * (D("1") - discount / D("100")),
        )
        operational = max(self.decimal(data.get("operational_reserve_per_token_usd")), D("0"))

        if promotional:
            infrastructure = max(self.decimal(data.get("infrastructure_capacity_per_token_usd")), D("0"))
            if infrastructure <= 0:
                raise ConflictException("Promotional tokens require a positive frozen infrastructure reserve.")
            effective_profit = D("0")
            data.update(
                {
                    "financial_snapshot_version": SNAPSHOT_VERSION,
                    "financial_economics_schema": ECONOMICS_SCHEMA,
                    "effective_paid_token_value_usd": "0",
                    "requested_effective_profit_per_token_usd": "0",
                    "effective_profit_per_token_usd": "0",
                    "infrastructure_capacity_per_token_usd": str(infrastructure),
                    "operational_reserve_per_token_usd": str(operational),
                    "infrastructure_reserve_source": "promotional_credit_pool",
                    "operational_reserve_source": "explicit_snapshot",
                    "profit_adjusted_to_protect_infrastructure": False,
                }
            )
            return data

        token_value = max(self.decimal(data.get("token_value_usd")), D("0"))
        has_protected_terms = token_value > 0 and normal_profit >= 0 and token_value > normal_profit
        if has_protected_terms:
            # Infrastructure belongs to the pricing rule, never to the discount.
            infrastructure = max(
                self.decimal(
                    data.get("infrastructure_capacity_per_token_usd"),
                    token_value - normal_profit,
                ),
                D("0"),
            )
            minimum_protected = infrastructure + operational
            if paid + EPSILON < minimum_protected:
                raise ConflictException(
                    "The paid amount does not cover the protected AI infrastructure and operational reserves."
                )
            maximum_real_profit = max(paid - minimum_protected, D("0"))
            effective_profit = max(min(requested_effective, maximum_real_profit), D("0"))
            infrastructure_source = "pricing_rule_fixed"
        else:
            # Compatibility for genuinely old/non-commercial credits. New V3 lots
            # must always arrive with explicit protected terms.
            effective_profit = max(min(requested_effective, paid), D("0"))
            infrastructure = max(paid - effective_profit - operational, D("0"))
            infrastructure_source = "legacy_paid_minus_profit"

        data.update(
            {
                "financial_snapshot_version": SNAPSHOT_VERSION,
                "financial_economics_schema": ECONOMICS_SCHEMA,
                "effective_paid_token_value_usd": str(paid),
                "requested_effective_profit_per_token_usd": str(max(requested_effective, D("0"))),
                "effective_profit_per_token_usd": str(effective_profit),
                "infrastructure_capacity_per_token_usd": str(infrastructure),
                "operational_reserve_per_token_usd": str(operational),
                "infrastructure_reserve_source": infrastructure_source,
                "operational_reserve_source": "explicit_snapshot",
                "profit_adjusted_to_protect_infrastructure": bool(
                    has_protected_terms and effective_profit < max(requested_effective, D("0"))
                ),
            }
        )
        return data

    def read_lot_snapshot(
        self,
        *,
        metadata: Mapping[str, Any] | None,
        paid_value_per_token: object,
        fallback_profit_per_token_usd: object = 0,
    ) -> TokenFinancialComponents:
        data = dict(metadata or {})
        paid = max(self.decimal(paid_value_per_token), D("0"))
        token_value = max(self.decimal(data.get("token_value_usd")), D("0"))
        normal_profit = max(self.decimal(data.get("normal_profit_per_token_usd")), D("0"))
        discount = min(max(self.decimal(data.get("profit_discount_percent")), D("0")), D("100"))
        has_frozen_profit = (
            data.get("effective_profit_per_token_usd") is not None
            or data.get("normal_profit_per_token_usd") is not None
        )
        if data.get("effective_profit_per_token_usd") is not None:
            effective_profit = max(self.decimal(data.get("effective_profit_per_token_usd")), D("0"))
        elif has_frozen_profit:
            effective_profit = normal_profit * (D("1") - discount / D("100"))
        else:
            effective_profit = min(
                max(self.decimal(fallback_profit_per_token_usd), D("0")),
                max(paid - EPSILON, D("0")),
            )

        operational = max(self.decimal(data.get("operational_reserve_per_token_usd")), D("0"))
        if data.get("infrastructure_capacity_per_token_usd") is not None:
            infrastructure = max(self.decimal(data.get("infrastructure_capacity_per_token_usd")), D("0"))
            source = "frozen_v3" if data.get("financial_economics_schema") == ECONOMICS_SCHEMA else "frozen_v2"
        elif token_value > 0 and normal_profit >= 0 and token_value > normal_profit:
            # Historical snapshot has base terms but predates explicit capacity.
            infrastructure = token_value - normal_profit
            source = "frozen_terms_compatibility"
        else:
            # Last-resort compatibility only. Do not use this path for new lots.
            infrastructure = max(paid - effective_profit - operational, D("0"))
            source = "legacy_current_rule_fallback" if not has_frozen_profit else "frozen_legacy"

        return TokenFinancialComponents(
            paid_value_per_token=paid,
            token_value_per_token=token_value,
            normal_profit_per_token=normal_profit,
            effective_profit_per_token=effective_profit,
            infrastructure_capacity_per_token=infrastructure,
            operational_reserve_per_token=operational,
            profit_discount_percent=discount,
            snapshot_source=source,
            metadata=data,
        )


token_financial_snapshot_service = TokenFinancialSnapshotService()
