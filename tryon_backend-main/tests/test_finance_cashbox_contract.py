from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def test_cashbox_routes_and_models_exist():
    text=(ROOT/'app/api/v1/endpoints/admin/finance_cashbox.py').read_text()
    for route in ['/cashbox','/token-bags','/withdrawals','/token-bag-expiration']:
        assert route in text
    model=(ROOT/'app/models/token_value_lot.py').read_text()
    for field in ['status','activated_at','expires_at','commercial_profit_released','released_expiration_usd']:
        assert field in model
def test_first_consumption_releases_profit():
    text=(ROOT/'app/services/token_value_ledger_service.py').read_text()
    assert 'lot.commercial_profit_released=True' in text
    assert 'lot.released_commercial_profit_usd=' in text
def test_refund_guard_uses_consumption_state():
    text=(ROOT/'app/services/token_purchase_service.py').read_text()
    assert 'already consumed tokens' in text
