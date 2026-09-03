
import asyncio
import time
from types import SimpleNamespace

import pytest

from app.common.exceptions import AppException
from app.services.modal_pipeline_adapter_service import ModalPipelineAdapterService


class _Status:
    def __init__(self, name):
        self.name = name


class _Node:
    def __init__(self, name):
        self.status = _Status(name)


class _AioMethod:
    def __init__(self, fn):
        self._fn = fn

    async def __call__(self, *args, **kwargs):
        return await self._fn(*args, **kwargs)


class _NeverGet:
    def __init__(self):
        self.aio = _AioMethod(self._wait)

    async def _wait(self, timeout=None):
        await asyncio.sleep(3600)


class _GraphMethod:
    def __init__(self, states):
        self._states = states
        self.aio = _AioMethod(self._read)

    async def _read(self):
        await asyncio.sleep(0)
        return [_Node(state) for state in self._states]


class _Call:
    def __init__(self, states):
        self.get = _NeverGet()
        self.get_call_graph = _GraphMethod(states)


class _FakeModal:
    class exception:
        class OutputExpiredError(Exception):
            pass

        class TimeoutError(Exception):
            pass


def _run_wait(service, call):
    async def restore(config, call_id, refresh=False):
        return call

    service._call_async = restore
    service._modal = lambda: _FakeModal
    return asyncio.run(
        service.await_result_async(
            SimpleNamespace(),
            call_id="fc-terminal-test",
            timeout_seconds=30,
        )
    )


def test_init_failure_is_detected_without_waiting_for_execution_timeout():
    service = ModalPipelineAdapterService()
    service._GRAPH_WATCH_INTERVAL_SECONDS = 0.01
    started = time.monotonic()

    with pytest.raises(AppException, match="INIT_FAILURE"):
        _run_wait(service, _Call(["INIT_FAILURE"]))

    assert time.monotonic() - started < 1.0


def test_success_without_result_payload_is_an_error():
    service = ModalPipelineAdapterService()
    service._GRAPH_WATCH_INTERVAL_SECONDS = 0.01
    service._SUCCESS_RESULT_GRACE_SECONDS = 0.02

    with pytest.raises(AppException, match="SUCCESS.*result payload"):
        _run_wait(service, _Call(["SUCCESS"]))


def test_generation_finalizer_still_requires_image_before_completed():
    source = (
        __import__("pathlib").Path("app/services/generation_module_runtime_service.py")
        .read_text(encoding="utf-8")
    )
    start = source.index("def finalize_modal_supervised")
    end = source.index("def _run_modal_module", start)
    block = source[start:end]

    assert block.index("self._assert_required_image_outputs") < block.index(
        'item.status = "completed"'
    )
