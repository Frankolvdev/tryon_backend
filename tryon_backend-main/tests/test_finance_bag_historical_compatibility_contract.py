from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def test_cancelled_fallback_reuses_the_same_explicit_component_builder():
    source=(ROOT/"app/services/token_value_ledger_service.py").read_text(encoding="utf-8")
    fallback=source[source.index("if tokens == 0 and expected > 0"):source.index("allocations=list(grouped.values())")]
    assert "apply_row(allocation,lot,take)" in fallback
    apply_start=source.index("def apply_row")
    apply_row=source[apply_start:source.index("for allocation,lot in rows", apply_start)]
    assert 'snapshot["infrastructure_capacity_per_token"]' in apply_row
    assert '"infrastructure_capacity_from_tokens_usd":0.0' in apply_row

def test_cashbox_uses_historical_financial_evidence_when_net_allocations_are_zero():
    source=(ROOT/"app/services/finance_cashbox_service.py").read_text(encoding="utf-8")
    assert "def _historical_bag_usage" in source
    assert "historical_consumed,_=self._historical_bag_usage" in source
    assert "if not gens:" in source
    assert "historical_reconstruction" in source

def test_fifo_mixed_bag_contract_remains_intact():
    source=(ROOT/"app/services/token_value_ledger_service.py").read_text(encoding="utf-8")
    assert ".order_by(TokenValueLot.created_at,TokenValueLot.id)" in source
    assert "take=min(max(needed,1),available)" in source
    assert "remaining=max(Decimal(\"0\"),remaining-provided)" in source
    assert ".order_by(TokenConsumptionAllocation.id.desc())" in source
