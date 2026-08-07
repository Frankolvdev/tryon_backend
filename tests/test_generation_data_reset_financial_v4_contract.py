from pathlib import Path


SERVICE = Path('app/services/generation_data_reset_service.py')


def _source() -> str:
    return SERVICE.read_text(encoding='utf-8')


def test_reset_covers_all_new_financial_activity_tables() -> None:
    source = _source()
    tables = (
        'infrastructure_provider_credit_releases',
        'infrastructure_funding_allocations',
        'infrastructure_funding_movements',
        'promotional_credit_returns',
        'promotional_token_grants',
        'promotional_credit_funds',
        'operational_expenses',
    )
    for table in tables:
        assert f'delete_all("{table}")' in source, table
        assert f'"{table}": self._count(db, "{table}")' in source, table


def test_reset_preserves_users_but_zeros_their_test_token_balance() -> None:
    source = _source()
    assert 'DELETE FROM "users"' not in source
    assert "delete_all(\"users\")" not in source
    assert 'UPDATE users SET token_balance = 0 WHERE token_balance <> 0' in source
    assert '"users_preserved": self._count(db, "users")' in source


def test_reset_preserves_account_avatar_files() -> None:
    source = _source()
    assert 'def _preserved_account_file_ids' in source
    assert 'SELECT avatar_file_id FROM users WHERE avatar_file_id IS NOT NULL' in source
    assert 'if int(value) not in preserved_file_ids' in source
    assert '"account_files_preserved": len(preserved_account_file_ids)' in source


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
    )
    for table in preserved_configuration:
        assert f'delete_all("{table}")' not in source, table


def test_reset_deletes_ledger_children_before_token_lots() -> None:
    source = _source()
    lot_pos = source.index('delete_all("token_value_lots")')
    dependent_tables = (
        'infrastructure_provider_credit_releases',
        'infrastructure_funding_allocations',
        'promotional_credit_returns',
        'promotional_token_grants',
        'token_consumption_allocations',
    )
    for table in dependent_tables:
        assert source.index(f'delete_all("{table}")') < lot_pos, table
