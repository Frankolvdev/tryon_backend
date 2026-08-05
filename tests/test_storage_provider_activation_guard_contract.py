from pathlib import Path


def test_activation_runs_health_check_before_updating_setting():
    source = Path("app/api/v1/endpoints/admin/storage.py").read_text(encoding="utf-8")
    health_pos = source.index("health = storage_service.health_check")
    update_pos = source.index('data={"value_string": selected}')
    assert health_pos < update_pos
    assert 'if not health.get("healthy")' in source


def test_local_health_response_has_visible_message():
    source = Path("app/services/storage_service.py").read_text(encoding="utf-8")
    assert '"message": f"Almacenamiento local disponible en {root}."' in source


def test_remote_health_response_has_message_fallback():
    source = Path("app/services/storage_service.py").read_text(encoding="utf-8")
    assert 'result.setdefault(' in source
    assert '"message"' in source
