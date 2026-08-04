from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def test_profit_per_token_core_contract():
 s=(ROOT/'app/services/pricing_service.py').read_text(); r=(ROOT/'app/services/generation_module_runtime_service.py').read_text(); f=(ROOT/'app/services/financial_protection_service.py').read_text()
 assert 'token_charge_for_infrastructure' in s
 assert 'token_value - profit_per_token' in s
 assert 'desired_profit_per_token_usd' in r
 assert 'desired_profit_per_token_usd' in f
 assert '_profit_per_token_diagnostics' in f
