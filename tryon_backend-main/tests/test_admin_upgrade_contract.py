from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_profit_simulator_keeps_operational_reserve_and_recommendation_value_bound_to_candidate():
    source = (ROOT / "app/services/pricing_simulator_service.py").read_text(encoding="utf-8")
    assert "operational_total = tokens *" in source
    assert "customer_value = tokens * (token_value +" in source
    assert "candidates.append((distance, abs(tv-base), scenario, tv, pp))" in source
    assert "token_value_usd=round(candidate_token_value, 6)" in source


def test_unused_settings_are_removed_from_defaults_and_cleanup_migration():
    defaults = (ROOT / "app/services/default_settings_service.py").read_text(encoding="utf-8")
    migration = (ROOT / "alembic/versions/05d_remove_unused_system_settings.py").read_text(encoding="utf-8")
    unused = (
        "app_environment",
        "max_login_attempts",
        "password_min_length",
        "active_payment_provider",
        "monthly_tokens_reset_enabled",
        "dynamic_pricing_enabled",
        "default_margin_percent",
        "scheduler_timezone",
        "analytics_enabled",
        "log_retention_days",
        "commercial_currency",
    )
    for key in unused:
        assert f'key="{key}"' not in defaults
        assert f'"{key}"' in migration
    # Settings that are consumed by the current platform must remain.
    for key in (
        "commercial_token_value_usd",
        "commercial_operational_reserve_per_token_usd",
        "commercial_execution_billing_policy",
        "free_signup_tokens",
        "promotional_signup_enabled",
        "promotional_allow_pending_settlement",
        "storage_provider",
        "scheduler_enabled",
    ):
        assert f'key="{key}"' in defaults


def test_user_generation_storage_delete_preserves_financial_history():
    service = (ROOT / "app/services/admin_user_storage_service.py").read_text(encoding="utf-8")
    endpoint = (ROOT / "app/api/v1/endpoints/admin/users.py").read_text(encoding="utf-8")
    assert 'generation-results/{execution_id}/%' in service
    assert "from app.models.generation_financial_record" not in service
    assert "from app.models.token_consumption_allocation" not in service
    assert '"financial_history_preserved": True' in service
    assert '"/users/{user_id}/generations/{execution_id}/storage"' in endpoint
    assert '"/users/{user_id}/storage-files"' in endpoint
    assert "total_size_bytes" in service
