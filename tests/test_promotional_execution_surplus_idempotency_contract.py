from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_execution_surplus_aggregates_multiple_allocations_from_same_promotional_lot():
    source = read("app/services/promotional_credit_service.py")
    assert "promo_by_lot: dict[int, dict] = {}" in source
    assert 'bucket=promo_by_lot.setdefault(key,{"lot":lot,"net":0})' in source
    assert 'bucket["net"]+=int(net)' in source
    assert "for bucket in promo_by_lot.values():" in source
    assert 'net=int(bucket["net"])' in source


def test_execution_surplus_keeps_database_idempotency_guard_and_row_lock():
    service = read("app/services/promotional_credit_service.py")
    model = read("app/models/promotional_credit.py")
    assert 'UniqueConstraint("grant_id", "reason", "reference_id", name="uq_promo_return_idempotency")' in model
    assert ".where(PromotionalTokenGrant.lot_id==lot.id)" in service
    assert ".with_for_update()" in service
    assert 'PromotionalCreditReturn.reason=="execution_surplus"' in service
    assert "db.flush()" in service


def test_reset_removes_all_promotional_runtime_financial_rows_before_parents():
    reset = read("app/services/generation_data_reset_service.py")
    ordered = [
        'delete_all("promotional_credit_returns")',
        'delete_all("promotional_token_grants")',
        'delete_all("promotional_funding_cycles")',
        'delete_all("promotional_funding_sources")',
        'delete_all("promotional_credit_funds")',
    ]
    positions = [reset.index(item) for item in ordered]
    assert positions == sorted(positions)
    assert '"promotional_credit_returns": self._count(db, "promotional_credit_returns")' in reset
    assert '"promotional_token_grants": self._count(db, "promotional_token_grants")' in reset
    assert '"promotional_funding_cycles": self._count(db, "promotional_funding_cycles")' in reset
    assert '"promotional_funding_sources": self._count(db, "promotional_funding_sources")' in reset
    assert '"promotional_credit_funds": self._count(db, "promotional_credit_funds")' in reset


def test_reset_still_preserves_users_and_account_files():
    reset = read("app/services/generation_data_reset_service.py")
    assert "UPDATE users SET token_balance = 0" in reset
    assert 'delete_all("users")' not in reset
    assert "avatar_file_id" in reset
    assert '"users_preserved": self._count(db, "users")' in reset
