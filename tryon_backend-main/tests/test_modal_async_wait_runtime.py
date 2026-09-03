import asyncio
from types import SimpleNamespace

from app.services.modal_pipeline_adapter_service import ModalPipelineAdapterService


class _AioGet:
    def __init__(self, output):
        self.output = output

    async def __call__(self, timeout=None):
        await asyncio.sleep(0)
        return self.output


class _Get:
    def __init__(self, output):
        self.aio = _AioGet(output)


class _Call:
    def __init__(self, output):
        self.get = _Get(output)


class _FakeModal:
    class exception:
        class OutputExpiredError(Exception):
            pass
        class TimeoutError(Exception):
            pass


def test_async_wait_returns_same_durable_call_without_polling_or_threads(monkeypatch):
    service = ModalPipelineAdapterService()
    output = {"runtime_contract": "tryon.generation-runtime/v1", "status": "completed"}
    call = _Call(output)
    monkeypatch.setattr(service, "_modal", lambda: _FakeModal)

    async def restore(config, call_id, refresh=False):
        return call

    monkeypatch.setattr(service, "_call_async", restore)

    result = asyncio.run(
        service.await_result_async(
            SimpleNamespace(),
            call_id="fc-test",
            timeout_seconds=30,
        )
    )
    assert result["provider_job_id"] == "fc-test"
    assert result["output"] == output


class _AsyncFactory:
    def __init__(self, client):
        self.client = client
        self.calls = 0

    async def __call__(self, token_id, token_secret):
        self.calls += 1
        await asyncio.sleep(0)
        return self.client


def test_async_client_creation_uses_modal_aio_interface(monkeypatch):
    service = ModalPipelineAdapterService()
    client = SimpleNamespace(is_closed=lambda: False)
    factory = _AsyncFactory(client)

    class _FromCredentials:
        aio = factory

    class _Client:
        from_credentials = _FromCredentials()

    class _ModalWithClient:
        Client = _Client

    monkeypatch.setattr(service, "_modal", lambda: _ModalWithClient)
    config = SimpleNamespace(token_id="ak-test", token_secret="as-test")

    resolved = asyncio.run(service._client_async(config))

    assert resolved is client
    assert factory.calls == 1


def test_async_wait_uses_async_call_restore_path(monkeypatch):
    service = ModalPipelineAdapterService()
    output = {"runtime_contract": "tryon.generation-runtime/v1", "status": "completed"}
    call = _Call(output)
    seen = {"async": 0}

    async def restore(config, call_id, refresh=False):
        seen["async"] += 1
        await asyncio.sleep(0)
        return call

    monkeypatch.setattr(service, "_modal", lambda: _FakeModal)
    monkeypatch.setattr(service, "_call_async", restore)
    monkeypatch.setattr(
        service,
        "_call",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("sync _call used in async wait")),
    )

    result = asyncio.run(
        service.await_result_async(
            SimpleNamespace(),
            call_id="fc-test-async-restore",
            timeout_seconds=30,
        )
    )

    assert result["output"] == output
    assert seen["async"] == 1
