from decimal import Decimal
from pathlib import Path

from app.services.infrastructure_cashbox_accounting import (
    calculate_expiration_infrastructure_split,
    calculate_infrastructure_funding_state,
)

ROOT = Path(__file__).resolve().parents[1]
SERVICE = (ROOT / "app/services/finance_cashbox_service.py").read_text(encoding="utf-8")
ENDPOINT = (ROOT / "app/api/v1/endpoints/admin/finance_cashbox.py").read_text(encoding="utf-8")
MIGRATION = (ROOT / "alembic/versions/05a_infrastructure_cashbox_fifo_allocations.py").read_text(encoding="utf-8")


def test_unfunded_cash_tracks_provider_mismatch_without_inventing_money():
    state = calculate_infrastructure_funding_state(
        protected_reserve_usd=Decimal("40"),
        infrastructure_used_by_provider_usd={"modal": Decimal("10")},
        funded_by_provider_usd={"runpod": Decimal("30")},
    )
    assert state.funded_usd == Decimal("30")
    assert state.unfunded_provider_cost_usd == Decimal("10")
    assert state.unfunded_future_reserve_usd == Decimal("10")
    assert state.unfunded_usd == Decimal("20")


def test_matching_provider_cost_consumes_funding_before_future_reserve():
    state = calculate_infrastructure_funding_state(
        protected_reserve_usd=Decimal("40"),
        infrastructure_used_by_provider_usd={"modal": Decimal("10")},
        funded_by_provider_usd={"modal": Decimal("30")},
    )
    assert state.matched_provider_cost_usd == Decimal("10")
    assert state.funded_against_future_reserve_usd == Decimal("20")
    assert state.unfunded_provider_cost_usd == Decimal("0")
    assert state.unfunded_future_reserve_usd == Decimal("20")


def test_expiration_only_moves_cash_still_in_bank_to_green_cashbox():
    split = calculate_expiration_infrastructure_split(
        protected_reserve_usd=Decimal("50"),
        infrastructure_used_by_provider_usd={},
        funding_allocations=[
            (1, "modal", Decimal("30")),
        ],
    )
    assert split.cash_release_usd == Decimal("20.000000")
    assert split.provider_credit_release_usd == Decimal("30.000000")
    assert split.credit_allocations[0].provider == "modal"


def test_expiration_keeps_matching_spend_out_of_released_provider_credit():
    split = calculate_expiration_infrastructure_split(
        protected_reserve_usd=Decimal("40"),
        infrastructure_used_by_provider_usd={"modal": Decimal("10")},
        funding_allocations=[
            (1, "modal", Decimal("30")),
        ],
    )
    assert split.cash_release_usd == Decimal("20.000000")
    assert split.provider_credit_release_usd == Decimal("20.000000")


def test_expiration_keeps_wrong_provider_credit_and_unfunded_cost_separate():
    split = calculate_expiration_infrastructure_split(
        protected_reserve_usd=Decimal("40"),
        infrastructure_used_by_provider_usd={"modal": Decimal("10")},
        funding_allocations=[
            (1, "runpod", Decimal("30")),
        ],
    )
    assert split.cash_release_usd == Decimal("10.000000")
    assert split.provider_credit_release_usd == Decimal("30.000000")



def test_prefunding_rounding_surplus_stays_provider_credit_not_green_cash():
    state = calculate_infrastructure_funding_state(
        protected_reserve_usd=Decimal("40"),
        infrastructure_used_by_provider_usd={"modal": Decimal("8")},
        funded_by_provider_usd={"modal": Decimal("50")},
    )
    assert state.provider_excess_credit_usd == Decimal("2")
    assert state.unfunded_usd == Decimal("0")


def test_partial_prefunding_leaves_rounding_surplus_in_bank():
    state = calculate_infrastructure_funding_state(
        protected_reserve_usd=Decimal("40"),
        infrastructure_used_by_provider_usd={"modal": Decimal("8")},
        funded_by_provider_usd={"modal": Decimal("30")},
    )
    assert state.provider_excess_credit_usd == Decimal("0")
    assert state.unfunded_future_reserve_usd == Decimal("18")

def test_funding_is_allocated_fifo_to_concrete_token_bags():
    assert ".order_by(TokenValueLot.created_at, TokenValueLot.id)" in SERVICE
    assert "InfrastructureFundingAllocation(" in SERVICE
    assert "lot_id=lot.id" in SERVICE
    assert "amount_usd=take" in SERVICE


def test_cashbox_never_counts_prefunded_rounding_as_withdrawable_cash():
    assert "provider_rounding_credit=min(" in SERVICE
    assert "cash_rounding=max(rounding-provider_rounding_credit" in SERVICE
    assert "realized_extra=cash_rounding" in SERVICE


def test_expiration_reuses_allocations_and_never_releases_funded_cash_as_profit():
    assert "lot.released_expiration_usd=expiration_split[\"cash_release_usd\"]" in SERVICE
    assert "InfrastructureProviderCreditRelease(" in SERVICE
    assert "provider_credit_released_by_provider" in SERVICE


def test_api_and_migration_preserve_full_audit_trail():
    assert "/infrastructure-fundings" in ENDPOINT
    for table in (
        "infrastructure_funding_movements",
        "infrastructure_funding_allocations",
        "infrastructure_provider_credit_releases",
    ):
        assert table in MIGRATION

def test_funded_bags_are_not_automatically_refundable():
    refund_service = (ROOT / "app/services/token_purchase_service.py").read_text(encoding="utf-8")
    assert "InfrastructureFundingAllocation" in refund_service
    assert "part of its AI reserve was already funded" in refund_service
    assert "has_infrastructure_funding" in SERVICE


def test_full_test_reset_removes_new_ledgers_before_token_bags():
    reset_service = (ROOT / "app/services/generation_data_reset_service.py").read_text(encoding="utf-8")
    release_pos = reset_service.index('delete_all("infrastructure_provider_credit_releases")')
    allocation_pos = reset_service.index('delete_all("infrastructure_funding_allocations")')
    movement_pos = reset_service.index('delete_all("infrastructure_funding_movements")')
    lot_pos = reset_service.index('delete_for_users("token_value_lots")')
    assert release_pos < allocation_pos < movement_pos < lot_pos



def test_expiration_and_funding_lock_bags_to_prevent_double_movements():
    assert SERVICE.count(".with_for_update()") >= 3
    assert ".order_by(TokenValueLot.created_at,TokenValueLot.id)" in SERVICE
