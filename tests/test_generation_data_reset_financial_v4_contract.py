from pathlib import Path


SERVICE = Path('app/services/generation_data_reset_service.py')


def _source() -> str:
    return SERVICE.read_text(encoding='utf-8')


def test_reset_covers_financial_test_activity_tables() -> None:
    source = _source()
    global_activity = (
        'infrastructure_provider_credit_releases',
        'infrastructure_funding_allocations',
        'infrastructure_funding_movements',
        'promotional_credit_returns',
        'promotional_token_grants',
        'promotional_credit_funds',
        'operational_expenses',
    )
    for table in global_activity:
        assert f'delete_all("{table}")' in source, table
        assert f'"{table}": self._count(db, "{table}")' in source, table


def test_reset_targets_only_final_users_and_preserves_admin_owner_accounts() -> None:
    source = _source()
    assert 'def _final_user_ids' in source
    assert "LOWER(COALESCE(role, 'user')) = 'user'" in source
    assert 'COALESCE(is_superuser, FALSE) = FALSE' in source
    assert 'DELETE FROM "users"' not in source
    assert 'delete_all("users")' not in source
    assert 'UPDATE users SET token_balance = 0 WHERE id = ANY(:user_ids) AND token_balance <> 0' in source


def test_reset_deletes_ai_models_and_user_creative_activity_only_for_target_users() -> None:
    source = _source()
    for table in ('ai_model_profiles', 'user_gallery_items', 'generation_module_executions', 'tryon_jobs'):
        assert f'delete_for_users("{table}")' in source, table
    assert 'delete_all("ai_model_profiles")' not in source
    assert 'delete_all("generation_module_executions")' not in source


def test_reset_storage_is_user_activity_scoped_and_preserves_account_and_configuration_media() -> None:
    source = _source()
    assert 'def _activity_file_ids' in source
    assert 'SELECT id FROM storage_files WHERE user_id = ANY(:user_ids)' in source
    assert 'def _preserved_account_file_ids' in source
    assert 'SELECT avatar_file_id FROM users WHERE avatar_file_id IS NOT NULL' in source
    assert 'def _preserved_configuration_file_ids' in source
    for table in ('ancestry_media_assets', 'model_generation_assets', 'body_proportion_presets', 'bubble_butt_presets'):
        assert f'"{table}"' in source
    assert 'preserved = self._preserved_account_file_ids(db) | self._preserved_configuration_file_ids(db)' in source


def test_reset_keeps_configuration_and_catalog_tables() -> None:
    source = _source()
    preserved_configuration = (
        'system_settings',
        'pricing_rules',
        'token_packages',
        'subscription_plans',
        'billing_coupons',
        'provider_gpu_prices',
        'generation_modules',
        'generation_module_inputs',
        'generation_module_outputs',
        'workflow_definitions',
        'runtime_builder_configs',
        'runtime_projects',
        'model_generation_assets',
        'ancestry_media_assets',
        'body_proportion_presets',
        'bubble_butt_presets',
        'promotional_funding_sources',
    )
    for table in preserved_configuration:
        assert f'delete_all("{table}")' not in source, table
        assert f'delete_for_users("{table}")' not in source, table


def test_promotional_source_policy_survives_but_generated_cycles_and_funds_reset() -> None:
    source = _source()
    assert 'delete_all("promotional_funding_cycles")' in source
    assert 'delete_all("promotional_credit_funds")' in source
    assert 'delete_all("promotional_funding_sources")' not in source
    assert '"promotional_funding_sources_preserved": self._count(db, "promotional_funding_sources")' in source


def test_reset_preserves_account_legal_acceptances_but_removes_checkout_acceptances() -> None:
    source = _source()
    assert "context IN ('token_checkout', 'subscription_checkout')" in source
    assert 'token_purchase_id IS NOT NULL' in source
    assert 'billing_payment_id IS NOT NULL' in source
    assert 'token_bag_id IS NOT NULL' in source
    assert 'delete_all("legal_acceptances")' not in source


def test_reset_scopes_stripe_side_effects_to_end_users() -> None:
    source = _source()
    assert 'WHERE user_id = ANY(:user_ids) AND provider_subscription_id IS NOT NULL' in source
    assert "WHERE user_id = ANY(:user_ids)" in source
    assert "AND provider = 'stripe'" in source


def test_reset_deletes_ledger_children_before_target_user_token_lots() -> None:
    source = _source()
    lot_pos = source.index('delete_for_users("token_value_lots")')
    dependent_markers = (
        'delete_all("infrastructure_provider_credit_releases")',
        'delete_all("infrastructure_funding_allocations")',
        'delete_all("promotional_credit_returns")',
        'delete_all("promotional_token_grants")',
        'delete_for_users("token_consumption_allocations")',
    )
    for marker in dependent_markers:
        assert source.index(marker) < lot_pos, marker


def test_reset_cleans_stale_user_activity_notifications_but_keeps_preferences_and_push_settings() -> None:
    source = _source()
    assert 'delete_for_users("user_notification_receipts")' in source
    assert 'delete_for_users("user_notifications", "recipient_user_id")' in source
    assert 'delete_for_users("support_tickets")' in source
    for table in ('user_notification_preferences', 'user_push_subscriptions', 'user_profile_settings', 'user_locale_preferences'):
        assert f'delete_all("{table}")' not in source
        assert f'delete_for_users("{table}")' not in source
