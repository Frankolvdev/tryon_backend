from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_storage_provider_contract_is_explicit():
    enums = (ROOT / "app/common/enums.py").read_text(encoding="utf-8")
    assert 'AMAZON_S3 = "amazon_s3"' in enums
    assert 'CLOUDFLARE_R2 = "cloudflare_r2"' in enums
    assert 'S3 = "s3"' in enums


def test_storage_engine_resolves_files_by_original_provider():
    source = (ROOT / "app/services/storage_service.py").read_text(encoding="utf-8")
    assert "def provider_for_file" in source
    assert "storage_file.provider" in source
    assert "def read_bytes" in source
    assert "def create_presigned_url" in source
    assert "def delete_file" in source
    assert '"cloudflare_r2"' in source
    assert '"amazon_s3"' in source


def test_generation_materializer_uses_storage_engine():
    materializer = (ROOT / "app/services/generation_module_file_materializer_service.py").read_text(encoding="utf-8")
    legacy_tryon = (ROOT / "app/services/comfyui_tryon_service.py").read_text(encoding="utf-8")
    assert "storage_service.read_bytes" in materializer
    assert "storage_service.read_bytes" in legacy_tryon
    assert 'Path("storage") / object_key' not in legacy_tryon


def test_independent_provider_configs_are_seeded_and_migrated():
    integrations = (ROOT / "app/services/integration_service.py").read_text(encoding="utf-8")
    migration = (ROOT / "alembic/versions/b7e4c1a9d210_add_multi_provider_storage_configs.py").read_text(encoding="utf-8")
    assert "IntegrationProvider.AMAZON_S3" in integrations
    assert "IntegrationProvider.CLOUDFLARE_R2" in integrations
    assert "amazon_s3" in migration
    assert "cloudflare_r2" in migration
