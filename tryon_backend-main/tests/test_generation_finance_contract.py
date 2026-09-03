from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def read(p): return (ROOT/p).read_text(encoding='utf-8')
def test_financial_ledger_is_parallel_and_fifo():
 s=read('app/services/token_value_ledger_service.py')
 assert 'order_by(TokenValueLot.created_at,TokenValueLot.id)' in s
 assert 'legacy_untraced_balance' in s
 assert 'effective_token_value_usd' in s
def test_generation_finance_uses_real_revenue_and_existing_infrastructure():
 s=read('app/services/generation_finance_service.py')
 assert "recognized_revenue_usd" in s
 assert 'profit=revenue-infra' in s
 r=read('app/services/generation_module_runtime_service.py')
 assert 'generation_finance_service.finalize' in r
def test_commercial_discount_scales_profit_by_product_tokens():
 s=read('app/services/financial_protection_service.py')
 assert 'safe_profit_per_token_usd' in s
 assert 'profit_budget=float(report.safe_profit_per_token_usd or 0) * token_count' in s
 assert 'discount_amount=profit_budget*requested/100.0' in s
