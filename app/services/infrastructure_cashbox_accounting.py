from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

D = Decimal


@dataclass(frozen=True)
class InfrastructureFundingState:
    funded_usd: Decimal
    matched_provider_cost_usd: Decimal
    funded_against_future_reserve_usd: Decimal
    unfunded_provider_cost_usd: Decimal
    unfunded_future_reserve_usd: Decimal
    provider_excess_credit_usd: Decimal

    @property
    def unfunded_usd(self) -> Decimal:
        return self.unfunded_provider_cost_usd + self.unfunded_future_reserve_usd


@dataclass(frozen=True)
class ExpirationCreditAllocation:
    funding_allocation_id: int
    provider: str
    amount_usd: Decimal


@dataclass(frozen=True)
class ExpirationInfrastructureSplit:
    cash_release_usd: Decimal
    provider_credit_release_usd: Decimal
    credit_allocations: tuple[ExpirationCreditAllocation, ...]


def calculate_infrastructure_funding_state(
    *,
    protected_reserve_usd: Decimal,
    infrastructure_used_by_provider_usd: dict[str, Decimal],
    funded_by_provider_usd: dict[str, Decimal],
) -> InfrastructureFundingState:
    protected = max(D(str(protected_reserve_usd or 0)), D("0"))
    used = {
        str(provider or "unknown").lower(): max(D(str(amount or 0)), D("0"))
        for provider, amount in infrastructure_used_by_provider_usd.items()
    }
    funded = {
        str(provider or "unknown").lower(): max(D(str(amount or 0)), D("0"))
        for provider, amount in funded_by_provider_usd.items()
    }
    matched = sum(
        min(funded.get(provider, D("0")), cost)
        for provider, cost in used.items()
    )
    funded_total = sum(funded.values())
    used_total = sum(used.values())
    remaining_funded = max(funded_total - matched, D("0"))
    funded_future = min(remaining_funded, protected)
    return InfrastructureFundingState(
        funded_usd=funded_total,
        matched_provider_cost_usd=matched,
        funded_against_future_reserve_usd=funded_future,
        unfunded_provider_cost_usd=max(used_total - matched, D("0")),
        unfunded_future_reserve_usd=max(protected - funded_future, D("0")),
        provider_excess_credit_usd=max(
            remaining_funded - funded_future,
            D("0"),
        ),
    )


def calculate_expiration_infrastructure_split(
    *,
    protected_reserve_usd: Decimal,
    infrastructure_used_by_provider_usd: dict[str, Decimal],
    funding_allocations: list[tuple[int, str, Decimal]],
) -> ExpirationInfrastructureSplit:
    protected = max(D(str(protected_reserve_usd or 0)), D("0")).quantize(D("0.000001"))
    used = {
        str(provider or "unknown").lower(): max(D(str(amount or 0)), D("0"))
        for provider, amount in infrastructure_used_by_provider_usd.items()
    }
    remaining = protected
    releases: list[ExpirationCreditAllocation] = []

    # Allocations arrive in FIFO order. Costs consume funding from the same provider
    # first; only unconsumed funded credit can remain trapped at a provider.
    for allocation_id, raw_provider, raw_amount in funding_allocations:
        provider = str(raw_provider or "unknown").lower()
        amount = max(D(str(raw_amount or 0)), D("0"))
        provider_used = used.get(provider, D("0"))
        consumed = min(amount, provider_used)
        used[provider] = max(provider_used - consumed, D("0"))
        free_credit = max(amount - consumed, D("0"))
        release = min(free_credit, remaining)
        if release <= 0:
            continue
        releases.append(
            ExpirationCreditAllocation(
                funding_allocation_id=int(allocation_id),
                provider=provider,
                amount_usd=release.quantize(D("0.000001")),
            )
        )
        remaining -= release
        if remaining <= 0:
            break

    credit = sum((row.amount_usd for row in releases), D("0")).quantize(D("0.000001"))
    return ExpirationInfrastructureSplit(
        cash_release_usd=max(protected - credit, D("0")).quantize(D("0.000001")),
        provider_credit_release_usd=credit,
        credit_allocations=tuple(releases),
    )
