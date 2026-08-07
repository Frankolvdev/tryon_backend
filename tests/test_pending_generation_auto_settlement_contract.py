from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_auto_settlement_reuses_manual_settlement_engine_and_does_not_reprice():
    source = read("app/services/pending_generation_settlement_service.py")
    assert "generation_module_runtime_service.settle_pending_billing" in source
    assert "token_charge_for_infrastructure" not in source
    assert "quote_fifo_infrastructure_charge" not in source
    assert "debit_tokens(" not in source


def test_auto_settlement_is_fifo_and_all_or_nothing_per_generation():
    source = read("app/services/pending_generation_settlement_service.py")
    assert "GenerationModuleExecution.created_at.asc()" in source
    assert "if int(user.token_balance or 0) < pending_tokens" in source
    assert "stopped_for_insufficient_balance" in source
    assert "break" in source


def test_only_paid_commercial_credits_trigger_auto_settlement():
    source = read("app/services/billing_service.py")
    assert 'purchase.status == TokenPurchaseStatus.CREDITED.value' in source
    assert 'trigger_source="stripe_token_purchase"' in source
    assert 'trigger_source="subscription_period_grant"' in source
    assert "pending_generation_settlement_service" in source
    # It must not be wired into the generic token credit service, because signup,
    # admin or future promotional credits need independent policies.
    token_source = read("app/services/token_service.py")
    assert "pending_generation_settlement_service" not in token_source


def test_paid_credit_survives_auto_settlement_failure():
    purchase = read("app/services/token_purchase_service.py")
    billing = read("app/services/billing_service.py")
    assert "purchase.status = TokenPurchaseStatus.CREDITED.value" in purchase
    assert "db.commit()" in purchase
    # The best-effort continuation lives in the webhook layer after the purchase
    # service has already committed the credit.
    assert "process_checkout_completed" in billing
    assert "settle_after_paid_credit" in billing
    service = read("app/services/pending_generation_settlement_service.py")
    assert "db.rollback()" in service
    assert "manual unlock endpoint" in service
