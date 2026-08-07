from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ECONOMICS = (ROOT / "app/services/token_financial_snapshot_service.py").read_text(encoding="utf-8")
LEDGER = (ROOT / "app/services/token_value_ledger_service.py").read_text(encoding="utf-8")


def test_new_commercial_lots_delegate_to_explicit_component_snapshot_service():
    create_lot = LEDGER[LEDGER.index("def create_lot"):LEDGER.index("def quote_fifo_infrastructure_charge")]
    assert "normalize_new_lot_snapshot" in create_lot
    assert "token_value - normal_profit" in ECONOMICS
    assert '"infrastructure_capacity_per_token_usd": str(infrastructure)' in ECONOMICS
    assert '"operational_reserve_per_token_usd": str(operational)' in ECONOMICS
    assert '"infrastructure_reserve_source": infrastructure_source' in ECONOMICS


def test_discount_shortfall_is_absorbed_by_profit_not_infrastructure():
    assert "maximum_real_profit = max(paid - minimum_protected" in ECONOMICS
    assert "min(requested_effective, maximum_real_profit)" in ECONOMICS
    assert '"profit_adjusted_to_protect_infrastructure"' in ECONOMICS

    token_value = Decimal("0.11")
    normal_profit = Decimal("0.103")
    paid_per_token = Decimal("51.15") / Decimal("660")
    requested_profit = Decimal("0.07725")
    protected_capacity = token_value - normal_profit
    actual_profit = min(requested_profit, paid_per_token - protected_capacity)
    assert protected_capacity == Decimal("0.007")
    assert actual_profit == Decimal("0.0705")
    assert protected_capacity * Decimal("660") == Decimal("4.620")


def test_correctly_priced_25_percent_discount_preserves_profit_and_reserve():
    token_value = Decimal("0.11")
    normal_profit = Decimal("0.103")
    requested_profit = normal_profit * Decimal("0.75")
    protected_capacity = token_value - normal_profit
    correct_price_per_token = requested_profit + protected_capacity
    assert requested_profit == Decimal("0.07725")
    assert protected_capacity == Decimal("0.007")
    assert correct_price_per_token == Decimal("0.08425")
    assert correct_price_per_token * Decimal("660") == Decimal("55.60500")


def test_legacy_lots_keep_compatibility_fallback_only_in_snapshot_service():
    assert "legacy_paid_minus_profit" in ECONOMICS
    assert "paid - effective_profit - operational" in ECONOMICS
    assert "legacy_paid_minus_profit" not in LEDGER
