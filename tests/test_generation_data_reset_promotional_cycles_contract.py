from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")

def test_reset_preview_counts_recurring_promotional_cycle_tables():
    service = read("app/services/generation_data_reset_service.py")
    assert '"promotional_funding_cycles": self._count(db, "promotional_funding_cycles")' in service
    assert '"promotional_funding_sources": self._count(db, "promotional_funding_sources")' in service

def test_reset_deletes_cycles_before_sources_and_funds():
    service = read("app/services/generation_data_reset_service.py")
    cycle = service.index('delete_all("promotional_funding_cycles")')
    source = service.index('delete_all("promotional_funding_sources")')
    fund = service.index('delete_all("promotional_credit_funds")')
    assert cycle < source < fund

def test_reset_still_preserves_users_and_account_files():
    service = read("app/services/generation_data_reset_service.py")
    assert 'UPDATE users SET token_balance = 0' in service
    assert 'users_preserved' in service
    assert 'account_files_preserved' in service
    assert 'avatar_file_id' in service
