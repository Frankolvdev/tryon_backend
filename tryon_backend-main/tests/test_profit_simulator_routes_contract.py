from pathlib import Path

def test_profit_simulator_routes_exist():
    text = Path('app/api/v1/endpoints/admin/pricing.py').read_text(encoding='utf-8')
    assert '/profit-simulator/simulate' in text
    assert '/profit-simulator/recommendations' in text
