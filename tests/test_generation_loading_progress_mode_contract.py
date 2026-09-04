from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_generation_loading_progress_mode_is_public_backend_default():
    source = (ROOT / "app/services/default_settings_service.py").read_text(encoding="utf-8")
    assert 'key="generation_loading_progress_mode"' in source
    assert 'value="backend"' in source
    assert 'default_value="backend"' in source
    assert 'is_public=True' in source
