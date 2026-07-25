from __future__ import annotations

import time
from typing import Any, Callable

import httpx

from app.common.exceptions import AppException
from app.schemas.infrastructure_provider import ModalProviderConfig


class ModalPipelineAdapterService:
    """HTTP transport for the full generation-runtime contract on Modal."""

    @staticmethod
    def _endpoint(config: ModalProviderConfig) -> str:
        base = str(config.runtime_url or "").strip().rstrip("/")
        if not base:
            raise AppException("Modal Runtime URL is not configured.")
        return f"{base}/api/tryon/pipeline"

    def execute_pipeline(
        self,
        config: ModalProviderConfig,
        *,
        payload: dict[str, Any],
        timeout_seconds: int,
        progress_callback: Callable[[float, str, dict[str, Any] | None], None] | None = None,
        cancellation_callback: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        if not config.enabled:
            raise AppException("Modal provider is disabled.")
        if cancellation_callback and cancellation_callback():
            raise InterruptedError("Modal execution cancelled before dispatch.")

        headers = {"Content-Type": "application/json"}
        if progress_callback:
            progress_callback(2.0, "Dispatching the complete pipeline to Modal.", {"provider_status": "DISPATCHING"})

        started = time.monotonic()
        try:
            with httpx.Client(
                timeout=httpx.Timeout(connect=60.0, read=float(timeout_seconds), write=300.0, pool=60.0),
                follow_redirects=True,
            ) as client:
                response = client.post(self._endpoint(config), json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise TimeoutError(f"Modal pipeline exceeded {timeout_seconds} seconds.") from exc
        except httpx.HTTPError as exc:
            raise AppException(f"Could not connect to Modal Runtime: {exc}") from exc

        if cancellation_callback and cancellation_callback():
            raise InterruptedError("Modal execution was cancelled while waiting for the remote result.")

        if response.status_code >= 400:
            detail = response.text.strip()
            try:
                body = response.json()
                detail = str(body.get("detail") or body.get("error") or detail)
            except Exception:
                pass
            raise AppException(f"Modal Runtime rejected the pipeline ({response.status_code}): {detail[:1000]}")

        try:
            output = response.json()
        except ValueError as exc:
            raise AppException("Modal Runtime returned a non-JSON response.") from exc
        if not isinstance(output, dict):
            raise AppException("Modal Runtime returned an invalid pipeline payload.")

        elapsed_ms = int((time.monotonic() - started) * 1000)
        if progress_callback:
            progress_callback(98.0, "Modal returned the complete pipeline result.", {"provider_status": "FINALIZING"})
        return {
            "provider": "modal",
            "output": output,
            "execution_time_ms": elapsed_ms,
            "runtime_url": str(config.runtime_url),
        }


modal_pipeline_adapter_service = ModalPipelineAdapterService()
