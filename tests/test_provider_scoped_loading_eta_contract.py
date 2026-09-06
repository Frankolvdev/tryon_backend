from pathlib import Path


def test_both_loading_eta_modes_are_provider_scoped():
    runtime = Path("app/services/generation_module_runtime_service.py").read_text(encoding="utf-8")
    pricing = Path("app/services/pricing_service.py").read_text(encoding="utf-8")

    assert "def historical_runtime_loading_duration(" in pricing
    assert "def historical_backend_loading_duration(" in pricing
    assert "module_id=module_id, status=\"completed\", engine=engine, skip=0, limit=5" in pricing
    assert "engine_key = engine.value" in runtime
    assert "historical_runtime_loading_duration(" in runtime
    assert "historical_backend_loading_duration(" in runtime
    assert runtime.count("engine=engine_key") >= 2


def test_loading_eta_fallback_does_not_reuse_learned_financial_estimate():
    runtime = Path("app/services/generation_module_runtime_service.py").read_text(encoding="utf-8")

    assert "pricing_rule_repository.get_for_generation_module(db, module.id)" in runtime
    assert 'getattr(pricing_rule, "initial_estimated_duration_seconds", None)' in runtime
    assert "loading_initial_duration_seconds" in runtime
    assert "int(pricing.estimated_duration_seconds or 30)" not in runtime


def test_financial_historical_estimator_remains_module_wide_and_unchanged():
    pricing = Path("app/services/pricing_service.py").read_text(encoding="utf-8")

    # Financial pricing must stay on the legacy module-wide estimator.  The UI-only
    # provider filters must not leak into pricing/tokens/cashbox calculations.
    assert "def _historical_duration(\n        self, module_id: int, fallback: int" in pricing
    financial_block = pricing.split("def _historical_duration(\n", 1)[1].split("def list_applied_rules", 1)[0]
    assert "engine=engine" not in financial_block
    assert 'status="completed"' in financial_block
    assert "estimate = max(duration for duration, _row in samples)" in financial_block
