from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def read(path:str)->str:
    return (ROOT/path).read_text(encoding="utf-8")


def test_promotional_tokens_are_provider_funded_zero_profit_lots():
    source=read("app/services/promotional_credit_service.py")
    assert '"normal_profit_per_token_usd": "0"' in source
    assert '"effective_profit_per_token_usd": "0"' in source
    assert '"promotional_credit_funded": True' in source
    assert '"infrastructure_capacity_per_token_usd": str(generation_reserve)' in source
    assert '"promotional_funding_per_token_usd": str(funding_per_token)' in source
    ledger=read("app/services/token_value_ledger_service.py")
    assert 'if bool(snapshot.get("promotional_credit_funded"))' in ledger
    assert 'effective_token_value_usd=Decimal("0")' in ledger


def test_promotional_pool_reserves_full_token_value_but_generation_math_keeps_protected_ai_reserve():
    source=read("app/services/promotional_credit_service.py")
    assert "Promotional tokens carry zero company profit" in source
    assert "return token_value" in source
    assert "generation_infrastructure_reserve_per_token" in source
    assert "reserve = (token_value - safe_profit)" in source
    assert '"infrastructure_capacity_per_token_usd": str(generation_reserve)' in source
    assert '"promotional_funding_per_token_usd": str(funding_per_token)' in source
    assert "token_charge_for_infrastructure" not in source


def test_signup_grant_is_backed_and_partial_only_when_pool_runs_out():
    source=read("app/services/promotional_credit_service.py")
    assert "grant_signup" in source
    assert 'grant_type="signup"' in source
    assert "allow_partial=True" in source
    assert "min(requested, max_tokens) if allow_partial else requested" in source
    user=read("app/services/user_service.py")
    oauth=read("app/services/oauth/flow.py")
    assert "promotional_credit_service.grant_signup" in user
    assert "promotional_credit_service.grant_signup" in oauth
    assert 'source="signup_bonus"' not in user


def test_manual_grant_is_exact_and_never_creates_unbacked_tokens():
    api=read("app/api/v1/endpoints/admin/finance_cashbox.py")
    assert "grant_type='manual_admin'" in api
    assert "allow_partial=False" in api
    service=read("app/services/promotional_credit_service.py")
    assert "if not allow_partial and max_tokens < requested" in service
    assert "no partial unbacked tokens were created" in service


def test_promotional_provider_scope_is_enforced_only_for_promotional_lots():
    ledger=read("app/services/token_value_ledger_service.py")
    assert "_lot_is_promotional" in ledger
    assert "if not self._lot_is_promotional(lot):" in ledger
    assert 'scope == "general" or not target or scope == target' in ledger
    billing=read("app/services/generation_module_billing_service.py")
    assert "allocation_provider=provider" in billing
    runtime=read("app/services/generation_module_runtime_service.py")
    assert "provider=(pricing.provider if pricing else None)" in runtime


def test_promotional_tokens_do_not_pay_old_debt_by_default_but_switch_can_allow_it():
    service=read("app/services/promotional_credit_service.py")
    assert '"promotional_allow_pending_settlement": ("boolean", False' in service
    runtime=read("app/services/generation_module_runtime_service.py")
    assert "if pending_settlement else True" in runtime
    assert "promotional_credit_service.allow_pending_settlement(db)" in runtime
    auto=read("app/services/pending_generation_settlement_service.py")
    assert "allow_pending_settlement" in auto
    assert "allow_promotional=allow_promotional" in auto


def test_promotional_expiration_returns_to_promo_pool_not_company_cash():
    cash=read("app/services/finance_cashbox_service.py")
    assert 'if lot.source == "promotional_credit"' in cash
    assert "promotional_credit_service.return_for_expired_lot" in cash
    assert 'lot.released_expiration_usd=D("0")' in cash
    assert 'commercial_lots=[lot for lot in lots if lot.source != "promotional_credit"]' in cash
    assert 'if lot.source == "promotional_credit":\n                continue' in cash


def test_unused_promotional_funding_returns_to_pool_and_company_rounding_stays_separate():
    runtime=read("app/services/generation_module_runtime_service.py")
    service=read("app/services/promotional_credit_service.py")
    assert "settle_execution_surplus" in runtime
    assert "settle_execution_surplus" in service
    assert "company_rounding_surplus_usd" in runtime
    assert '"promotional_credit_returned_usd"' in runtime
    assert '"profit_rounding_surplus_usd": round(company_rounding_surplus_usd' in runtime
    assert "actual_share=(infra*D(net)/D(total_tokens))" in service


def test_promotional_tables_are_reset_with_test_activity():
    reset=read("app/services/generation_data_reset_service.py")
    assert 'delete_all("promotional_credit_returns")' in reset
    assert 'delete_all("promotional_token_grants")' in reset
    assert 'delete_all("promotional_credit_funds")' in reset


def test_migration_is_linear_after_infrastructure_cashbox():
    migration=read("alembic/versions/05b_promotional_credit_cashbox.py")
    assert 'revision = "05b_promo_credits"' in migration
    assert 'down_revision = "05a_infra_cashbox"' in migration
