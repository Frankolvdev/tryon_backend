from __future__ import annotations

from decimal import Decimal
from typing import Any

D = Decimal


def _money(value: Any) -> D:
    try:
        return D(str(value or 0))
    except Exception:
        return D("0")


def calculate_profitability_surplus(
    *,
    allocations: list[dict] | None,
    desired_profit_per_token_usd: float | Decimal | None,
    infrastructure_cost_usd: float | Decimal | None,
    rounding_surplus_usd: float | Decimal | None,
    profit_applied: bool = True,
) -> tuple[list[dict], D]:
    """Return FIFO allocations annotated with the confirmed profitability surplus.

    This is intentionally separate from token rounding.  A commercial token bag is
    born with a historical *normal* profit per token (the safe commercial floor at
    purchase time).  A later generation may use a pricing rule with a higher target
    profit.  The difference becomes confirmable only when those exact tokens are
    consumed.

    Safety rules:
    - promotional tokens never create commercial profit;
    - a no-profit execution never creates this surplus;
    - compare against normal (pre-benefit) bag profit, never effective profit, so a
      coupon/plan discount is not silently recovered;
    - cap the surplus by historical infrastructure capacity actually freed after
      the generation's attributed infrastructure cost and existing rounding.  This
      prevents double counting and protects historical bags if token economics later
      change.
    """
    rows = [dict(row) for row in (allocations or [])]
    desired = max(_money(desired_profit_per_token_usd), D("0"))
    infrastructure = max(_money(infrastructure_cost_usd), D("0"))
    rounding = max(_money(rounding_surplus_usd), D("0"))

    total_capacity = sum(
        max(
            _money(
                row.get("infrastructure_capacity_from_tokens_usd")
                or row.get("infrastructure_capacity_used_usd")
            ),
            D("0"),
        )
        for row in rows
    )

    total_surplus = D("0")
    for row in rows:
        tokens = max(int(row.get("tokens_used") or row.get("tokens") or 0), 0)
        normal_profit = max(_money(row.get("normal_profit_per_token_usd")), D("0"))
        capacity = max(
            _money(
                row.get("infrastructure_capacity_from_tokens_usd")
                or row.get("infrastructure_capacity_used_usd")
            ),
            D("0"),
        )
        promotional = str(row.get("source") or "").lower() == "promotional_credit"

        candidate = D("0")
        cap = D("0")
        if profit_applied and not promotional and tokens > 0 and desired > normal_profit:
            candidate = (desired - normal_profit) * tokens
            share = capacity / total_capacity if total_capacity > 0 else D("0")
            attributed_infrastructure = infrastructure * share
            attributed_rounding = rounding * share
            cap = max(capacity - attributed_infrastructure - attributed_rounding, D("0"))

        surplus = min(candidate, cap) if candidate > 0 else D("0")
        per_token = surplus / tokens if tokens > 0 else D("0")
        row["desired_profit_per_token_usd"] = float(desired)
        row["profitability_surplus_candidate_usd"] = float(candidate)
        row["profitability_surplus_cap_usd"] = float(cap)
        row["profitability_surplus_per_token_usd"] = float(per_token)
        row["profitability_surplus_usd"] = float(surplus)
        total_surplus += surplus

    return rows, total_surplus
