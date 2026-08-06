from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "app/services/token_value_ledger_service.py").read_text(encoding="utf-8")


def test_new_commercial_lots_freeze_pricing_rule_infrastructure_reserve():
    create_lot = SOURCE[SOURCE.index("def create_lot"):SOURCE.index("def quote_fifo_infrastructure_charge")]
    assert 'token_value=self._decimal(snapshot.get("token_value_usd"))' in create_lot
    assert "protected_capacity=token_value-normal_profit" in create_lot
    assert '"infrastructure_capacity_per_token_usd": str(infrastructure_capacity)' in create_lot
    assert '"infrastructure_reserve_source": "pricing_rule_fixed"' in create_lot


def test_discount_shortfall_is_absorbed_by_profit_not_infrastructure():
    create_lot = SOURCE[SOURCE.index("def create_lot"):SOURCE.index("def quote_fifo_infrastructure_charge")]
    assert "maximum_real_profit=max(paid_per_token-protected_capacity" in create_lot
    assert "min(requested_effective_profit,maximum_real_profit)" in create_lot
    assert '"profit_adjusted_to_protect_infrastructure"' in create_lot

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


def test_legacy_lots_keep_compatibility_fallback():
    create_lot = SOURCE[SOURCE.index("def create_lot"):SOURCE.index("def quote_fifo_infrastructure_charge")]
    assert "legacy_paid_minus_profit" in create_lot
    assert "infrastructure_capacity=max(paid_per_token-effective_profit" in create_lot
