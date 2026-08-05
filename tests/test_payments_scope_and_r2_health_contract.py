from pathlib import Path


def test_payment_history_service_accepts_record_scope():
    source = Path("app/services/billing_history_service.py").read_text(encoding="utf-8")
    assert 'record_scope: str = "processed"' in source
    assert 'record_scope=record_scope' in source
    assert '_payment_commercial_summary' in source


def test_r2_health_uses_object_listing_and_clear_diagnostics():
    source = Path("app/services/s3_storage_service.py").read_text(encoding="utf-8")
    assert "list_objects_v2(Bucket=bucket, MaxKeys=1)" in source
    assert "Cloudflare R2 no encontró el bucket" in source
    assert "el dominio público" in source
