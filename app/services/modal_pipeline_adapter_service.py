from __future__ import annotations

import threading
import time
from typing import Any, Callable

import httpx
from fastapi.encoders import jsonable_encoder

from app.common.exceptions import AppException
from app.schemas.infrastructure_provider import ModalProviderConfig


class ModalTransientTransportError(AppException):
    """Temporary network failure that must not fail a running GPU job."""


class ModalPipelineAdapterService:
    """FunctionCall-based transport for Modal generation jobs.

    A single pooled HTTP client is intentionally reused. Creating a new client
    for every poll exhausted ephemeral sockets on Windows and produced
    WinError 10055 while the remote FunctionCall was still healthy.
    """

    def __init__(self) -> None:
        self._client_lock = threading.Lock()
        self._client = httpx.Client(
            timeout=httpx.Timeout(connect=30.0, read=60.0, write=60.0, pool=30.0),
            limits=httpx.Limits(max_connections=40, max_keepalive_connections=20, keepalive_expiry=30.0),
            transport=httpx.HTTPTransport(retries=3),
            follow_redirects=True,
            trust_env=False,
        )

    @staticmethod
    def _base(config: ModalProviderConfig) -> str:
        base = str(config.runtime_url or "").strip().rstrip("/")
        if not base:
            raise AppException("Modal Runtime URL is not configured.")
        return base

    def _url(self, config: ModalProviderConfig, suffix: str) -> str:
        return f"{self._base(config)}/api/tryon/pipeline{suffix}"

    @staticmethod
    def _detail(response: httpx.Response) -> str:
        detail = response.text.strip()
        try:
            body = response.json()
            if isinstance(body, dict):
                detail = str(body.get("detail") or body.get("error") or detail)
        except Exception:
            pass
        return detail[:1000]

    def _request(self, method: str, url: str, *, attempts: int = 4, **kwargs: Any) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                # httpx.Client is thread-safe; the lock only protects recovery
                # if Windows invalidates the pool after a low-level socket error.
                return self._client.request(method, url, **kwargs)
            except (httpx.TransportError, OSError) as exc:
                last_error = exc
                if attempt + 1 < attempts:
                    time.sleep(min(2.0, 0.25 * (2 ** attempt)))
                    continue
        raise ModalTransientTransportError(str(last_error or "Unknown Modal transport error."))

    def submit_pipeline(self, config: ModalProviderConfig, *, payload: dict[str, Any]) -> str:
        if not config.enabled:
            raise AppException("Modal provider is disabled.")
        try:
            response = self._request(
                "POST",
                self._url(config, "/submit"),
                json=jsonable_encoder(payload),
                headers={"Content-Type": "application/json"},
            )
        except ModalTransientTransportError as exc:
            raise AppException(f"Could not submit the Modal FunctionCall: {exc}") from exc
        if response.status_code >= 400:
            raise AppException(
                f"Modal Runtime rejected the pipeline submission ({response.status_code}): {self._detail(response)}"
            )
        body = response.json()
        call_id = str(body.get("call_id") or "").strip() if isinstance(body, dict) else ""
        if not call_id:
            raise AppException("Modal Runtime did not return a FunctionCall ID.")
        return call_id

    def poll_result(self, config: ModalProviderConfig, *, call_id: str) -> tuple[bool, dict[str, Any] | None]:
        try:
            response = self._request("GET", self._url(config, f"/result/{call_id}"))
        except ModalTransientTransportError as exc:
            raise ModalTransientTransportError(
                f"Could not poll Modal FunctionCall {call_id}: {exc}"
            ) from exc
        if response.status_code == 202:
            return False, None
        if response.status_code >= 400:
            raise AppException(
                f"Modal FunctionCall result failed ({response.status_code}): {self._detail(response)}"
            )
        body = response.json()
        if not isinstance(body, dict):
            raise AppException("Modal Runtime returned an invalid FunctionCall result.")
        if body.get("status") == "cancelled":
            raise InterruptedError("Modal FunctionCall cancellation confirmed.")
        return True, body

    def cancel_call(
        self,
        config: ModalProviderConfig,
        *,
        call_id: str,
        timeout_seconds: int = 90,
    ) -> dict[str, Any]:
        try:
            response = self._request(
                "POST",
                self._url(config, f"/cancel/{call_id}"),
                attempts=5,
                json={"terminate_containers": False, "wait_timeout_seconds": timeout_seconds},
                timeout=httpx.Timeout(connect=30.0, read=float(timeout_seconds) + 30.0, write=30.0, pool=30.0),
            )
        except ModalTransientTransportError as exc:
            raise AppException(f"Could not cancel Modal FunctionCall {call_id}: {exc}") from exc
        if response.status_code >= 400:
            raise AppException(
                f"Modal FunctionCall cancellation failed ({response.status_code}): {self._detail(response)}"
            )
        body = response.json()
        if not isinstance(body, dict) or body.get("status") != "cancelled" or not body.get("confirmed"):
            raise AppException("Modal did not confirm FunctionCall cancellation.")
        return body

    def execute_pipeline(
        self,
        config: ModalProviderConfig,
        *,
        payload: dict[str, Any],
        timeout_seconds: int,
        progress_callback: Callable[[float, str, dict[str, Any] | None], None] | None = None,
        cancellation_callback: Callable[[], bool] | None = None,
        submitted_callback: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        if cancellation_callback and cancellation_callback():
            raise InterruptedError("Modal execution cancelled before dispatch.")
        if progress_callback:
            progress_callback(2.0, "Submitting Modal FunctionCall.", {"provider_status": "DISPATCHING"})
        started = time.monotonic()
        call_id = self.submit_pipeline(config, payload=payload)
        if submitted_callback:
            submitted_callback(call_id)
        if progress_callback:
            progress_callback(5.0, "Modal FunctionCall accepted.", {
                "provider_status": "IN_QUEUE", "provider_job_id": call_id
            })

        deadline = started + float(timeout_seconds)
        last_progress = 5.0
        poll_interval = 2.0
        consecutive_transport_errors = 0
        last_progress_notice = 0.0
        while time.monotonic() < deadline:
            try:
                ready, output = self.poll_result(config, call_id=call_id)
                consecutive_transport_errors = 0
            except ModalTransientTransportError as exc:
                # A local socket/buffer failure says nothing about the remote GPU
                # job. Keep the execution running and retry with backoff.
                consecutive_transport_errors += 1
                if progress_callback and consecutive_transport_errors in {1, 5, 10}:
                    progress_callback(last_progress, "Modal status connection interrupted; retrying.", {
                        "provider_status": "RUNNING",
                        "provider_job_id": call_id,
                        "transport_warning": str(exc),
                    })
                time.sleep(min(10.0, 1.5 * consecutive_transport_errors))
                continue
            if ready:
                elapsed_ms = int((time.monotonic() - started) * 1000)
                if progress_callback:
                    progress_callback(98.0, "Modal FunctionCall completed.", {
                        "provider_status": "FINALIZING", "provider_job_id": call_id
                    })
                return {
                    "provider": "modal",
                    "output": output,
                    "execution_time_ms": elapsed_ms,
                    "runtime_url": str(config.runtime_url),
                    "provider_job_id": call_id,
                }
            time.sleep(poll_interval)
            poll_interval = min(6.0, poll_interval + 0.5)
            last_progress = min(90.0, last_progress + 0.25)
            now = time.monotonic()
            if progress_callback and now - last_progress_notice >= 5.0:
                last_progress_notice = now
                progress_callback(last_progress, "Modal FunctionCall is running.", {
                    "provider_status": "RUNNING", "provider_job_id": call_id
                })
        raise TimeoutError(f"Modal FunctionCall {call_id} exceeded {timeout_seconds} seconds.")


modal_pipeline_adapter_service = ModalPipelineAdapterService()
