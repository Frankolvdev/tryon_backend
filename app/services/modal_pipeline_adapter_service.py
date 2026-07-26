from __future__ import annotations

import time
from typing import Any, Callable

import httpx
from fastapi.encoders import jsonable_encoder

from app.common.exceptions import AppException
from app.schemas.infrastructure_provider import ModalProviderConfig


class ModalPipelineAdapterService:
    """FunctionCall-based transport for Modal generation jobs."""

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

    def submit_pipeline(self, config: ModalProviderConfig, *, payload: dict[str, Any]) -> str:
        if not config.enabled:
            raise AppException("Modal provider is disabled.")
        try:
            with httpx.Client(timeout=httpx.Timeout(60.0), follow_redirects=True) as client:
                response = client.post(
                    self._url(config, "/submit"),
                    json=jsonable_encoder(payload),
                    headers={"Content-Type": "application/json"},
                )
        except httpx.HTTPError as exc:
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
            with httpx.Client(timeout=httpx.Timeout(60.0), follow_redirects=True) as client:
                response = client.get(self._url(config, f"/result/{call_id}"))
        except httpx.HTTPError as exc:
            raise AppException(f"Could not poll Modal FunctionCall {call_id}: {exc}") from exc
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
            with httpx.Client(
                timeout=httpx.Timeout(connect=60.0, read=float(timeout_seconds) + 30.0, write=60.0, pool=60.0),
                follow_redirects=True,
            ) as client:
                response = client.post(
                    self._url(config, f"/cancel/{call_id}"),
                    json={"terminate_containers": True, "wait_timeout_seconds": timeout_seconds},
                )
        except httpx.HTTPError as exc:
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
        poll_interval = 1.5
        while time.monotonic() < deadline:
            if cancellation_callback and cancellation_callback():
                # The API cancellation path performs FunctionCall.cancel(). Keep polling
                # until Modal confirms cancellation or returns a final result.
                pass
            ready, output = self.poll_result(config, call_id=call_id)
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
            poll_interval = min(4.0, poll_interval + 0.25)
            last_progress = min(90.0, last_progress + 0.25)
            if progress_callback:
                progress_callback(last_progress, "Modal FunctionCall is running.", {
                    "provider_status": "RUNNING", "provider_job_id": call_id
                })
        raise TimeoutError(f"Modal FunctionCall {call_id} exceeded {timeout_seconds} seconds.")


modal_pipeline_adapter_service = ModalPipelineAdapterService()
