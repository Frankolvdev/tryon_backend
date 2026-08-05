from pathlib import Path


def test_storage_admin_supports_three_provider_configuration():
    source = Path("app/api/v1/endpoints/admin/storage.py").read_text(encoding="utf-8")
    assert '@router.patch("/storage/providers/{provider}")' in source
    assert '"amazon_s3"' in source
    assert '"cloudflare_r2"' in source
    assert '"local_storage_dir"' in source
    assert 'active_provider' in source
