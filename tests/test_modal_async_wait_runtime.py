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
    monkeypatch.setattr(service, "_call", lambda config, call_id, refresh=False: call)

    result = asyncio.run(
        service.await_result_async(
            SimpleNamespace(),
            call_id="fc-test",
            timeout_seconds=30,
        )
    )
    assert result["provider_job_id"] == "fc-test"
    assert result["output"] == output
