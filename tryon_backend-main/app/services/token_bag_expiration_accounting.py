from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

D = Decimal


@dataclass(frozen=True)
class TokenBagExpirationAmounts:
    commercial_profit_released_usd: Decimal
    infrastructure_reserve_released_usd: Decimal


def calculate_token_bag_expiration_amounts(
    *,
    original_tokens: int,
    remaining_tokens: int,
    infrastructure_capacity_per_token_usd: Decimal,
    effective_profit_per_token_usd: Decimal,
    commercial_profit_released: bool,
    released_commercial_profit_usd: Decimal,
) -> TokenBagExpirationAmounts:
    """Separate commercial profit from unused infrastructure on expiration.

    Caja adds these two buckets independently.  Therefore the expiration bucket
    must contain only the AI reserve attached to tokens that actually expire.
    """
    original = max(int(original_tokens or 0), 0)
    remaining = max(int(remaining_tokens or 0), 0)
    total_profit = (D(str(effective_profit_per_token_usd)) * original).quantize(D("0.000001"))
    existing_profit = D(str(released_commercial_profit_usd or 0)).quantize(D("0.000001"))
    commercial_release = existing_profit if commercial_profit_released and existing_profit > 0 else total_profit
    infrastructure_release = (
        D(str(infrastructure_capacity_per_token_usd)) * remaining
    ).quantize(D("0.000001"))
    return TokenBagExpirationAmounts(
        commercial_profit_released_usd=commercial_release,
        infrastructure_reserve_released_usd=infrastructure_release,
    )
