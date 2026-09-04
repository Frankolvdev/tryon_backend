from types import SimpleNamespace

from app.services.generation_execution_state_contract import generation_execution_state_contract


def execution(status: str, cancel_requested: bool = False):
    return SimpleNamespace(status=status, cancel_requested=cancel_requested)


def test_client_active_excludes_cancellation_pending_execution():
    assert generation_execution_state_contract.is_active_for_client(execution("queued"))
    assert generation_execution_state_contract.is_active_for_client(execution("running"))
    assert not generation_execution_state_contract.is_active_for_client(execution("queued", True))
    assert not generation_execution_state_contract.is_active_for_client(execution("running", True))


def test_only_uncancelled_queued_execution_is_dispatchable():
    assert generation_execution_state_contract.is_dispatchable(execution("queued"))
    assert not generation_execution_state_contract.is_dispatchable(execution("queued", True))
    assert not generation_execution_state_contract.is_dispatchable(execution("running"))


def test_cancellation_pending_execution_stays_reconcilable_but_not_client_active():
    item = execution("running", True)
    assert generation_execution_state_contract.needs_terminal_reconciliation(item)
    assert not generation_execution_state_contract.is_active_for_client(item)
    assert not generation_execution_state_contract.is_terminal(item)


def test_terminal_states_are_never_active_or_dispatchable():
    for status in ("completed", "failed", "cancelled"):
        item = execution(status)
        assert generation_execution_state_contract.is_terminal(item)
        assert not generation_execution_state_contract.is_active_for_client(item)
        assert not generation_execution_state_contract.is_dispatchable(item)
