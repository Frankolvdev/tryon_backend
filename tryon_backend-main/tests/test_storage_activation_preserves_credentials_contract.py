from pathlib import Path


def test_integration_updates_preserve_omitted_or_masked_credentials():
    source = Path("app/services/integration_service.py").read_text(encoding="utf-8")
    assert 'if field in {"api_key", "api_secret", "webhook_secret"}' in source
    assert 'if value is None:' in source
    assert '"********"' in source
    assert '"••••••••"' in source


def test_storage_activation_still_runs_health_before_switching_provider():
    source = Path("app/api/v1/endpoints/admin/storage.py").read_text(encoding="utf-8")
    health_pos = source.index("health = storage_service.health_check")
    update_pos = source.index('data={"value_string": selected}')
    assert health_pos < update_pos
