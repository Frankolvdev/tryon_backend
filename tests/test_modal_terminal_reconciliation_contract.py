import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.common.exceptions import AppException
from app.services.modal_pipeline_adapter_service import ModalPipelineAdapterService


class _AioMethod:
    def __init__(self, fn):
        self._fn = fn

    async def __call__(self, *args, **kwargs):
        return await self._fn(*args, **kwargs)


class _Get:
    def __init__(self, fn):
        self.aio = _AioMethod(fn)


class _FakeModal:
    class exception:
        class OutputExpiredError(Exception):
            pass

        class TimeoutError(Exception):
            pass


def test_modal_async_wait_is_event_driven_without_call_graph_polling():
    service = ModalPipelineAdapterService()
    calls = {"get": 0, "graph": 0}

    async def get_result(timeout=None):
        calls["get"] += 1
        return {"status": "completed", "outputs": {"image": "ok"}}

    class Call:
        get = _Get(get_result)

        async def get_call_graph(self):
            calls["graph"] += 1
            raise AssertionError("normal result supervision must not poll the call graph")

    async def restore(config, call_id, refresh=False):
        assert call_id == "fc-event-driven"
        return Call()

    service._call_async = restore
    service._modal = lambda: _FakeModal

    result = asyncio.run(
        service.await_result_async(
            SimpleNamespace(),
            call_id="fc-event-driven",
            timeout_seconds=30,
        )
    )

    assert result["provider_job_id"] == "fc-event-driven"
    assert calls == {"get": 1, "graph": 0}


def test_terminal_provider_error_fails_same_call_without_generation_retry():
    service = ModalPipelineAdapterService()
    get_calls = 0

    async def fail_result(timeout=None):
        nonlocal get_calls
        get_calls += 1
        raise RuntimeError("provider execution failed")

    class Call:
        get = _Get(fail_result)

    async def restore(config, call_id, refresh=False):
        assert call_id == "fc-failed-once"
        return Call()

    service._call_async = restore
    service._modal = lambda: _FakeModal

    with pytest.raises(AppException, match="provider execution failed"):
        asyncio.run(
            service.await_result_async(
                SimpleNamespace(),
                call_id="fc-failed-once",
                timeout_seconds=30,
            )
        )

    assert get_calls == 1


def test_generation_finalizer_still_requires_image_before_completed():
    source = Path("app/services/generation_module_runtime_service.py").read_text(encoding="utf-8")
    start = source.index("def finalize_modal_supervised")
    end = source.index("def _run_modal_module", start)
    block = source[start:end]

    assert block.index("self._assert_required_image_outputs") < block.index(
        'item.status = "completed"'
    )
