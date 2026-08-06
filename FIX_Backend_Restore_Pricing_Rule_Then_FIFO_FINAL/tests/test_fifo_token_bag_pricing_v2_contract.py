from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_pricing_rule_drives_token_quantity_and_fifo_only_allocates():
    pricing = (ROOT / "app/services/pricing_service.py").read_text(encoding="utf-8")
    ledger = (ROOT / "app/services/token_value_ledger_service.py").read_text(encoding="utf-8")
    runtime = (ROOT / "app/services/generation_module_runtime_service.py").read_text(encoding="utf-8")

    assert "def token_charge_for_infrastructure" in pricing
    assert "capacity = token_value - profit_per_token" in pricing
    assert "def allocate" in ledger
    assert "order_by(TokenValueLot.created_at,TokenValueLot.id)" in ledger

    # Regression guard: lot discounts/profit snapshots must never decide how
    # many tokens a generation costs.
    assert "quote_fifo_infrastructure_charge(" not in runtime
    assert "pricing_service.token_charge_for_infrastructure(" in runtime
    assert '"token_charge_basis": "current_pricing_rule_then_fifo_allocation"' in runtime


def test_fifo_snapshots_remain_available_for_profit_and_discount_traceability():
    ledger = (ROOT / "app/services/token_value_ledger_service.py").read_text(encoding="utf-8")
    assert '"financial_snapshot_version": 2' in ledger
    assert '"effective_profit_per_token_usd"' in ledger
    assert '"profit_discount_percent"' in ledger
    assert '"coupon_code"' in ledger
    assert '"plan_name"' in ledger
    assert "def execution_summary" in ledger

