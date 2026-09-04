from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_cancelled_fallback_reuses_the_same_explicit_component_builder():
    source = (ROOT / "app/services/token_value_ledger_service.py").read_text(encoding="utf-8")
    fallback = source[source.index("if tokens == 0 and expected > 0"):source.index("allocations=list(grouped.values())")]
    assert "apply_row(allocation,lot,take)" in fallback
    apply_start = source.index("def apply_row")
    apply_row = source[apply_start:source.index("for allocation,lot in rows", apply_start)]
    assert 'snapshot["infrastructure_capacity_per_token"]' in apply_row
    assert '"infrastructure_capacity_from_tokens_usd":0.0' in apply_row


def test_cashbox_reuses_immutable_generation_breakdown_for_historical_bag_usage():
    source = (ROOT / "app/services/finance_cashbox_service.py").read_text(encoding="utf-8")
    assert "def _generation_rows_for_bag" in source
    assert "raw_parts=breakdown.get('token_bags_used') or []" in source
    assert "bag_parts=[" in source
    assert "historical_consumed=sum(int(x['tokens_used']) for x in generation_rows)" in source
    assert "consumed=max(int(lot.original_tokens or 0)-int(lot.remaining_tokens or 0),historical_consumed,0)" in source


def test_fifo_mixed_bag_contract_remains_intact():
    source = (ROOT / "app/services/token_value_ledger_service.py").read_text(encoding="utf-8")
    assert ".order_by(TokenValueLot.created_at,TokenValueLot.id)" in source
    assert "take=min(max(needed,1),available)" in source
    assert "remaining=max(Decimal(\"0\"),remaining-provided)" in source
    assert ".order_by(TokenConsumptionAllocation.id.desc())" in source
