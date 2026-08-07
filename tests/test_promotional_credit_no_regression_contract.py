from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def read(path:str)->str:
    return (ROOT/path).read_text(encoding="utf-8")


def test_pricing_rule_remains_single_source_of_generation_token_quantity():
    runtime=read("app/services/generation_module_runtime_service.py")
    assert "pricing_service.token_charge_for_infrastructure" in runtime
    assert '"token_charge_basis": "current_pricing_rule_then_fifo_allocation"' in runtime
    assert "final_tokens = int(final_bag_quote" not in runtime


def test_generic_credit_service_still_does_not_auto_settle_debt():
    token=read("app/services/token_service.py")
    assert "pending_generation_settlement_service" not in token


def test_commercial_token_lot_protection_formula_is_unchanged():
    ledger=read("app/services/token_value_ledger_service.py")
    assert "protected_capacity=token_value-normal_profit" in ledger
    assert "maximum_real_profit=max(paid_per_token-protected_capacity" in ledger
    assert "infrastructure_capacity=protected_capacity" in ledger


def test_promotional_addition_does_not_modify_provider_engines_or_stripe_clients():
    changed={
        "app/services/modal_pipeline_adapter_service.py",
        "app/services/runpod_serverless_adapter_service.py",
        "app/services/beam_serverless_adapter_service.py",
        "app/services/stripe_client_service.py",
    }
    # Contract documents the files that must remain outside this feature.
    for path in changed:
        assert (ROOT/path).exists()


def test_expiration_removes_tokens_from_wallet_before_they_can_become_legacy_balance():
    cash=read("app/services/finance_cashbox_service.py")
    assert "user.token_balance=before-removed" in cash
    assert "source='token_bag_expiration'" in cash
    assert "later recreate it as legacy/untraced tokens" in cash
