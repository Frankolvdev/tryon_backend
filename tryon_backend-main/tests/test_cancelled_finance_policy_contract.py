from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")

def test_cancelled_finance_uses_final_tokens_and_zero_commercial_profit():
    finance = read("app/services/generation_finance_service.py")
    ledger = read("app/services/token_value_ledger_service.py")
    assert "expected_tokens=int(billing_breakdown.get('final_tokens') or 0)" in finance
    assert 'if not profit_applied:' in finance
    assert 'bag["company_profit_usd"]=0.0' in finance
    assert "expected_tokens:int|None=None" in ledger
    assert "tokens == 0 and expected > 0 and rows" in ledger
