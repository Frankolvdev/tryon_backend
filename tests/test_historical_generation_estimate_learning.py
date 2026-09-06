from pathlib import Path


def test_estimate_uses_maximum_valid_completed_generation():
    source = Path("app/services/pricing_service.py").read_text(encoding="utf-8")
    assert 'status="completed"' in source
    assert 'limit=5' in source
    assert 'if not samples:' in source
    assert 'return float(fallback), "initial", 0, "low", None' in source
    assert 'if len(durations) >= 4:' in source
    assert 'filtered = [item for item in samples if lower <= item[0] <= upper]' in source
    assert 'estimate = max(duration for duration, _row in samples)' in source
    assert '"historical_max"' in source
    assert 'count >= 5' in source
    assert 'count >= 2' in source
    assert '"historical_weighted_average"' not in source
    assert 'weight = count - index' not in source


def test_module_contract_exposes_estimate_explanation():
    schema = Path("app/schemas/generation_module.py").read_text(encoding="utf-8")
    service = Path("app/services/generation_module_service.py").read_text(encoding="utf-8")
    for field in ("historical_samples_used", "estimate_confidence", "estimate_updated_at"):
        assert field in schema
        assert field in service


def test_backend_loading_eta_is_provider_scoped_without_changing_pricing_estimator():
    pricing = Path("app/services/pricing_service.py").read_text(encoding="utf-8")
    runtime = Path("app/services/generation_module_runtime_service.py").read_text(encoding="utf-8")
    assert 'status="completed", engine=engine, skip=0, limit=5' in pricing
    assert 'engine == "owner_local"' in pricing
    assert 'accounting_mode != "owner_private"' in pricing
    assert 'engine=engine.value if hasattr(engine, "value") else str(engine)' in runtime
    # Financial/provider-duration pricing learning remains on its original module-wide path.
    assert 'def _historical_duration(\n        self, module_id: int, fallback: int' in pricing
    assert 'estimate = max(duration for duration, _row in samples)' in pricing
