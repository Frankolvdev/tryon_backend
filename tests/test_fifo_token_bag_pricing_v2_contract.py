from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_fifo_bag_snapshots_drive_initial_and_final_token_charge():
    ledger = (ROOT / "app/services/token_value_ledger_service.py").read_text(encoding="utf-8")
    runtime = (ROOT / "app/services/generation_module_runtime_service.py").read_text(encoding="utf-8")
    assert "def quote_fifo_infrastructure_charge" in ledger
    assert '"infrastructure_capacity_per_token_usd"' in ledger
    assert '"financial_snapshot_version": 2' in ledger
    assert 'segment_source":"already_allocated"' not in ledger  # values are emitted dynamically, not hard-coded fixtures
    assert "estimated_bag_quote = token_value_ledger_service.quote_fifo_infrastructure_charge" in runtime
    assert "final_bag_quote = token_value_ledger_service.quote_fifo_infrastructure_charge" in runtime
    assert '"token_charge_basis": "fifo_token_bag_snapshots"' in runtime


def test_fifo_quote_preserves_policy_and_legacy_compatibility():
    ledger = (ROOT / "app/services/token_value_ledger_service.py").read_text(encoding="utf-8")
    assert "snapshot[\"effective_profit_per_token\"] if apply_profit else Decimal(\"0\")" in ledger
    assert "legacy_current_rule_fallback" in ledger
    assert "with_for_update()" in ledger
    assert "ROUND_CEILING" in ledger
    assert "do not contain enough funded infrastructure capacity" in ledger
