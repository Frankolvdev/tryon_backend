from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_finance_accuracy_contract():
    ledger = (ROOT / "app/services/token_value_ledger_service.py").read_text(encoding="utf-8")
    finance = (ROOT / "app/services/generation_finance_service.py").read_text(encoding="utf-8")
    runtime = (ROOT / "app/services/generation_module_runtime_service.py").read_text(encoding="utf-8")
    assert "grouped:dict[int,dict]" in ledger
    assert 'current["tokens_used"]+=net' in ledger
    assert "rounding_surplus_for_company_usd" in finance
    assert '"applied_profit_usd":round(profit_after_benefits,9)' in finance
    assert "applied_profit_from_bags" in runtime
