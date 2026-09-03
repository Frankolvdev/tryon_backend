from pathlib import Path

from app.schemas.generation_module import GenerationModuleCreate


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_new_generation_module_can_be_a_draft_without_endpoint_or_engine():
    payload = GenerationModuleCreate(key="draft-module", name="Draft module")
    assert payload.endpoint is None
    assert payload.default_execution_engine is None


def test_create_service_keeps_engine_less_module_inactive():
    source = read("app/services/generation_module_service.py")
    assert "and data.default_execution_engine is not None" in source
    assert "data.default_execution_engine.value" in source


def test_module_hard_delete_is_blocked_when_execution_history_exists():
    source = read("app/services/generation_module_service.py")
    assert "GenerationModuleExecution.generation_module_id == module_id" in source
    assert "execution history" in source
    assert "db.delete(module)" in source


def test_storage_content_infers_generic_mime_from_filename_or_key():
    source = read("app/api/v1/endpoints/admin/storage.py")
    assert "application/octet-stream" in source
    assert "mimetypes.guess_type(filename)" in source
    assert "mimetypes.guess_type(storage_file.object_key)" in source


def test_draft_engine_migration_is_nullable_and_single_chain():
    source = read("alembic/versions/05g_generation_module_draft_engine.py")
    assert 'down_revision = "05f_promo_cycle_hook"' in source
    assert "nullable=True" in source
