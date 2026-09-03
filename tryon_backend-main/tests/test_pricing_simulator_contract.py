from pathlib import Path


def test_pricing_simulator_contract_is_wired():
    root = Path(__file__).resolve().parents[1]
    endpoint = (root / "app/api/v1/endpoints/admin/pricing.py").read_text(encoding="utf-8")
    service = (root / "app/services/pricing_simulator_service.py").read_text(encoding="utf-8")
    schema = (root / "app/schemas/pricing_simulator.py").read_text(encoding="utf-8")
    assert '@router.post("/pricing-simulator"' in endpoint
    assert "pricing_simulator_service.simulate" in endpoint
    assert "math.ceil(infra / capacity)" in service
    assert "PricingSimulatorRecommendation" in schema
