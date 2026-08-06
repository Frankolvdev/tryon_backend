from decimal import Decimal
from pathlib import Path

from app.services.token_bag_expiration_accounting import calculate_token_bag_expiration_amounts

ROOT=Path(__file__).resolve().parents[1]
SERVICE=(ROOT/'app/services/finance_cashbox_service.py').read_text(encoding='utf-8')
ENDPOINT=(ROOT/'app/api/v1/endpoints/admin/finance_cashbox.py').read_text(encoding='utf-8')
CONFIG=(ROOT/'app/core/config.py').read_text(encoding='utf-8')


def test_expiration_never_mixes_commercial_profit_into_expiration_release():
    assert "lot.released_expiration_usd=amounts.infrastructure_reserve_released_usd" in SERVICE
    assert "release += snap['effective_profit_per_token']" not in SERVICE
    assert "lot.released_commercial_profit_usd=amounts.commercial_profit_released_usd" in SERVICE


def test_expiration_simulation_is_non_production_admin_only_and_explicit():
    assert 'TEST_FORCE_TOKEN_BAG_EXPIRATION: bool = False' in CONFIG
    assert "settings.APP_ENV.lower() in {'production','prod'}" in SERVICE
    assert "not settings.TEST_FORCE_TOKEN_BAG_EXPIRATION" in SERVICE
    assert "if not data.confirm" in ENDPOINT
    assert "Depends(admin_guard)" in ENDPOINT


def test_expiration_uses_one_shared_accounting_path():
    assert 'def _expire_lot' in SERVICE
    assert 'self._expire_lot(db,lot,expired_at=now)' in SERVICE
    assert "result=self._expire_lot(db,lot,expired_at=now)" in SERVICE


def test_never_used_bag_releases_profit_and_reserve_once():
    amounts=calculate_token_bag_expiration_amounts(
        original_tokens=100,
        remaining_tokens=100,
        infrastructure_capacity_per_token_usd=Decimal('0.007'),
        effective_profit_per_token_usd=Decimal('0.103'),
        commercial_profit_released=False,
        released_commercial_profit_usd=Decimal('0'),
    )
    assert amounts.commercial_profit_released_usd==Decimal('10.300000')
    assert amounts.infrastructure_reserve_released_usd==Decimal('0.700000')
    assert amounts.commercial_profit_released_usd+amounts.infrastructure_reserve_released_usd==Decimal('11.000000')


def test_partially_used_bag_only_releases_unused_ai_reserve():
    amounts=calculate_token_bag_expiration_amounts(
        original_tokens=100,
        remaining_tokens=95,
        infrastructure_capacity_per_token_usd=Decimal('0.007'),
        effective_profit_per_token_usd=Decimal('0.103'),
        commercial_profit_released=True,
        released_commercial_profit_usd=Decimal('10.300000'),
    )
    assert amounts.commercial_profit_released_usd==Decimal('10.300000')
    assert amounts.infrastructure_reserve_released_usd==Decimal('0.665000')


def test_historical_repair_is_capped_to_full_ai_reserve_only():
    assert "current_expiration_release>max_expiration_release" in SERVICE
    assert "lot.released_expiration_usd=max_expiration_release" in SERVICE
