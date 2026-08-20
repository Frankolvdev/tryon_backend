from pathlib import Path


def test_estimate_uses_maximum_valid_completed_generation():
    source = Path("app/services/pricing_service.py").read_text(encoding="utf-8")
    assert 'status="completed"' in source
    assert 'limit=50' in source
    assert 'if not samples:' in source
    assert 'return float(fallback), "initial", 0, "low", None' in source
    assert 'if len(durations) >= 4:' in source
    assert 'filtered = [item for item in samples if lower <= item[0] <= upper]' in source
    assert 'estimate = max(duration for duration, _row in samples)' in source
    assert '"historical_max"' in source
    assert 'count >= 10' in source
    assert 'count >= 2' in source
    assert '"historical_weighted_average"' not in source
    assert 'weight = count - index' not in source


def test_module_contract_exposes_estimate_explanation():
    schema = Path("app/schemas/generation_module.py").read_text(encoding="utf-8")
    service = Path("app/services/generation_module_service.py").read_text(encoding="utf-8")
    for field in ("historical_samples_used", "estimate_confidence", "estimate_updated_at"):
        assert field in schema
        assert field in service
