from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_pricing_rule_drives_token_quantity_and_fifo_only_allocates():
    pricing = read("app/services/pricing_service.py")
    economics = read("app/services/token_financial_snapshot_service.py")
    ledger = read("app/services/token_value_ledger_service.py")
    runtime = read("app/services/generation_module_runtime_service.py")

    assert "def token_charge_for_infrastructure" in pricing
    assert "generation_infrastructure_capacity(" in pricing
    assert "capacity = token_value - normal_profit" in economics
    assert "def allocate" in ledger
    assert "order_by(TokenValueLot.created_at,TokenValueLot.id)" in ledger

    # Lot discounts/profit snapshots never decide how many tokens a generation costs.
    assert "quote_fifo_infrastructure_charge(" not in runtime
    assert "pricing_service.token_charge_for_infrastructure(" in runtime
    assert '"token_charge_basis": "current_pricing_rule_then_fifo_allocation"' in runtime


def test_fifo_snapshots_are_explicit_components_and_keep_traceability():
    economics = read("app/services/token_financial_snapshot_service.py")
    ledger = read("app/services/token_value_ledger_service.py")
    assert 'SNAPSHOT_VERSION = 3' in economics
    assert 'ECONOMICS_SCHEMA = "explicit_components_v3"' in economics
    assert '"infrastructure_capacity_per_token_usd"' in economics
    assert '"operational_reserve_per_token_usd"' in economics
    assert '"effective_profit_per_token_usd"' in economics
    assert '"profit_discount_percent"' in economics
    assert "def execution_summary" in ledger
