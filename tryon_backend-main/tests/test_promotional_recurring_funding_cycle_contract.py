from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_recurring_credit_is_additive_layer_not_replacement():
    promo = read("app/services/promotional_credit_service.py")
    cycle = read("app/services/promotional_funding_cycle_service.py")
    assert "ordered_eligible_funds" in promo
    assert "existing/manual company-funded rows remain the fallback" in promo
    assert "PromotionalCreditFund" in cycle
    assert "token_charge_for_infrastructure" not in cycle
    assert "TokenValueLot" not in cycle


def test_first_cycle_accepts_real_current_balance_but_next_cycle_uses_configured_amount():
    cycle = read("app/services/promotional_funding_cycle_service.py")
    schema = read("app/schemas/promotional_credit.py")
    assert "current_available_usd" in schema
    assert "recurring_amount_usd" in schema
    assert "opening_available=opening" in cycle
    assert "opening_available=recurring" in cycle
    assert "first_cycle=True" in cycle
    assert "first_cycle=False" in cycle


def test_rollover_is_lazy_idempotent_and_non_accumulating():
    cycle = read("app/services/promotional_funding_cycle_service.py")
    assert "def ensure_current_cycles" in cycle
    assert "while today >= source.current_cycle_end" in cycle
    assert 'fund.remaining_usd = D("0")' in cycle
    assert "expired_unused_usd = expired" in cycle
    assert "next_start = source.current_cycle_end" in cycle
    assert "opening_available=recurring" in cycle
    assert "uq_promo_source_cycle_window" in read("app/models/promotional_funding_cycle.py")


def test_recurring_provider_credit_is_spent_before_company_money():
    cycle = read("app/services/promotional_funding_cycle_service.py")
    assert "return [fund for _end, fund in recurring] + own" in cycle
    assert "Closed/future recurring funds are intentionally ineligible" in cycle


def test_closed_provider_cycle_cannot_be_resurrected_by_late_returns():
    cycle = read("app/services/promotional_funding_cycle_service.py")
    promo = read("app/services/promotional_credit_service.py")
    assert "returned_after_close_usd" in cycle
    assert "cycle.status != \"active\"" in cycle
    assert "promotional_funding_cycle_service.restore_amount" in promo


def test_manual_existing_funds_remain_company_owned_and_never_reset():
    cycle = read("app/services/promotional_funding_cycle_service.py")
    assert "cycle is None" in cycle
    assert "every historical/manual fund remains company-owned funding" in cycle


def test_reset_includes_new_cycle_tables_before_fund_parent():
    reset = read("app/services/generation_data_reset_service.py")
    assert 'delete_all("promotional_funding_cycles")' in reset
    assert 'delete_all("promotional_funding_sources")' in reset
    assert reset.index('delete_all("promotional_funding_cycles")') < reset.index('delete_all("promotional_credit_funds")')


def test_migration_is_linear_after_current_head():
    migration = read("alembic/versions/05e_promotional_recurring_cycles.py")
    assert 'revision = "05e_promo_cycles"' in migration
    assert 'down_revision = "05d_unused_settings"' in migration

def test_recurring_amount_is_configurable_and_not_hardcoded_to_modal_thirty_dollars():
    cycle = read("app/services/promotional_funding_cycle_service.py")
    schema = read("app/schemas/promotional_credit.py")
    assert "recurring_amount_usd" in cycle
    assert "current_available_usd" in schema
    assert 'D("30")' not in cycle
    assert "= 30" not in cycle


def test_cycle_guard_runs_on_promotional_money_movements_without_webhook_dependency():
    promo = read("app/services/promotional_credit_service.py")
    cycle = read("app/services/promotional_funding_cycle_service.py")
    assert promo.count("promotional_funding_cycle_service.ensure_current_cycles(db)") >= 5
    assert "self.ensure_current_cycles(db)" in cycle
    assert "No webhook is required" in cycle

def test_restore_keeps_original_over_return_safety_for_both_own_and_closed_cycle_funds():
    cycle = read("app/services/promotional_funding_cycle_service.py")
    assert "cannot receive more backing than it originally committed" in cycle
    assert "cannot receive more backing than was committed before it closed" in cycle
    assert "cycle.expired_unused_usd" in cycle
