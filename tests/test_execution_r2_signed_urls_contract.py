from pathlib import Path


def test_execution_endpoints_hydrate_storage_urls():
    root = Path(__file__).parents[1]
    service = (root / "app/services/generation_execution_media_service.py").read_text()
    endpoint = (root / "app/api/v1/endpoints/generation_modules.py").read_text()
    assert "create_presigned_url" in service
    assert 'hydrated["preview_url"] = readable_url' in service
    assert 'hydrated["download_url"] = readable_url' in service
    assert "generation_execution_media_service.hydrate_many" in endpoint
    assert "generation_execution_media_service.hydrate(db, execution)" in endpoint


def test_storage_supports_generation_asset_filter():
    root = Path(__file__).parents[1]
    endpoint = (root / "app/api/v1/endpoints/admin/storage.py").read_text()
    repository = (root / "app/repositories/storage_file_repository.py").read_text()
    assert "asset_kind" in endpoint
    assert 'generation-inputs/%' in repository
    assert 'generation-results/%' in repository
