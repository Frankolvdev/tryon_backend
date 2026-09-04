from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_cashbox_cards_have_read_only_movement_history_endpoint():
    endpoint = read("app/api/v1/endpoints/admin/finance_cashbox.py")
    service = read("app/services/finance_cashbox_movement_service.py")
    assert "'/cashbox/movements/{cashbox_key}'" in endpoint
    assert "finance_cashbox_movement_service.history" in endpoint
    assert '"utility": "Dinero libre para ti"' in service
    assert '"infrastructure_cash": "IA aún en tu caja"' in service
    assert '"infrastructure_funded": "IA ya enviada"' in service
    assert '"pending_recovery": "Cobros pendientes"' in service
    assert '"blocked_profit": "Ganancia todavía en espera"' in service
    assert '"withdrawals": "Dinero ya retirado"' in service
    assert '"operational": "Gastos disponibles"' in service


def test_utility_history_keeps_profitability_and_rounding_separate():
    service = read("app/services/finance_cashbox_movement_service.py")
    assert 'kind="profitability_surplus"' in service
    assert 'kind="rounding_surplus"' in service
    assert 'remaining_profitability' in service
    assert 'remaining_rounding' in service
    assert 'kind="withdrawal"' in service


def test_history_reconciles_against_same_card_source_of_truth():
    service = read("app/services/finance_cashbox_movement_service.py")
    assert 'summary = finance_cashbox_service.summary(db)' in service
    assert '"reconciled": self._q(current) == self._q(running)' in service
    assert 'mode="current_composition"' in service
