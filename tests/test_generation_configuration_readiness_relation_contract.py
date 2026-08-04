from pathlib import Path

SERVICE = Path('app/services/generation_configuration_readiness_service.py').read_text(encoding='utf-8')


def test_readiness_resolves_pricing_rule_through_repository():
    assert 'pricing_rule_repository.get_for_generation_module(db, module.id)' in SERVICE
    assert 'module.pricing_rule_id' not in SERVICE


def test_readiness_still_checks_exact_gpu_price():
    assert 'provider_pricing_service.get_cost' in SERVICE
    assert 'gpu_key=gpu_key' in SERVICE
    assert 'gpu_cost is None or gpu_cost <= 0' in SERVICE


def test_readiness_remains_before_side_effects():
    runtime = Path('app/services/generation_module_runtime_service.py').read_text(encoding='utf-8')
    gate = runtime.index('generation_configuration_readiness_service.ensure_ready')
    charge = runtime.index('generation_module_billing_service.charge')
    persist = runtime.index('generation_module_execution_store_service.save')
    submit = runtime.index('generation_job_orchestrator_service.submit')
    assert gate < charge < persist < submit
