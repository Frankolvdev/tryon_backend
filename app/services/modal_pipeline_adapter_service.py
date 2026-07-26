from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

from fastapi.encoders import jsonable_encoder

from app.common.exceptions import AppException
from app.schemas.infrastructure_provider import ModalProviderConfig


logger = logging.getLogger(__name__)


class ModalTransientTransportError(AppException):
    """Temporary Modal control-plane failure that must not fail a healthy GPU job."""


class ModalPipelineAdapterService:
    """Direct Modal SDK transport for deployed ComfyUIServer FunctionCalls.

    The Backend is the control plane. No CPU ``runtime_api`` web container is
    deployed or contacted. The only Modal container used by generation is the
    GPU-backed ``ComfyUIServer`` class.
    """

    _TERMINAL_GRAPH_STATES = {"SUCCESS", "FAILURE", "INIT_FAILURE", "TERMINATED", "TIMEOUT"}

    def __init__(self) -> None:
        self._client_lock = threading.Lock()
        self._clients: dict[tuple[str, str], Any] = {}

    @staticmethod
    def _modal() -> Any:
        try:
            import modal
        except ImportError as exc:
            raise AppException(
                "Modal Python SDK is not installed in the Backend environment."
            ) from exc
        return modal

    def _client(self, config: ModalProviderConfig) -> Any:
        token_id = str(config.token_id or "").strip()
        token_secret = str(config.token_secret or "").strip()
        if not token_id or not token_secret:
            raise AppException("Modal credentials are not configured.")
        key = (token_id, token_secret)
        with self._client_lock:
            client = self._clients.get(key)
            if client is None or bool(getattr(client, "is_closed", lambda: False)()):
                client = self._modal().Client.from_credentials(token_id, token_secret)
                self._clients[key] = client
            return client

    @staticmethod
    def _validate_config(config: ModalProviderConfig) -> None:
        if not config.enabled:
            raise AppException("Modal provider is disabled.")
        if not str(config.app_name or "").strip():
            raise AppException("Modal App name is not configured.")

    def _worker(self, config: ModalProviderConfig) -> Any:
        self._validate_config(config)
        modal = self._modal()
        try:
            cls = modal.Cls.from_name(
                str(config.app_name).strip(),
                "ComfyUIServer",
                environment_name=str(config.environment or "main").strip() or "main",
                client=self._client(config),
            )
            return cls()
        except Exception as exc:
            raise AppException(
                f"Could not resolve ComfyUIServer in Modal App {config.app_name} "
                f"(environment {config.environment or 'main'}). Redeploy the runtime with the "
                f"configured App name so Modal and the Backend use the same deployment: {exc}"
            ) from exc

    def _call(self, config: ModalProviderConfig, call_id: str) -> Any:
        call_id = str(call_id or "").strip()
        if not call_id:
            raise AppException("Modal FunctionCall ID is missing.")
        try:
            return self._modal().FunctionCall.from_id(call_id, client=self._client(config))
        except Exception as exc:
            raise AppException(f"Could not restore Modal FunctionCall {call_id}: {exc}") from exc

    @staticmethod
    def _is_cancelled_exception(exc: BaseException) -> bool:
        text = f"{exc.__class__.__name__}: {exc}".lower()
        return "cancel" in text or "terminated" in text

    @staticmethod
    def _graph_status_name(node: Any) -> str:
        status = getattr(node, "status", None)
        name = getattr(status, "name", None)
        if name:
            return str(name).upper()
        text = str(status or "").upper()
        return text.rsplit(".", 1)[-1]

    def submit_pipeline(self, config: ModalProviderConfig, *, payload: dict[str, Any]) -> str:
        try:
            call = self._worker(config).run_pipeline.spawn(jsonable_encoder(payload))
        except Exception as exc:
            raise AppException(f"Could not submit the Modal FunctionCall: {exc}") from exc
        call_id = str(getattr(call, "object_id", "") or "").strip()
        if not call_id:
            raise AppException("Modal did not return a FunctionCall ID.")
        return call_id

    def poll_result(self, config: ModalProviderConfig, *, call_id: str) -> tuple[bool, dict[str, Any] | None]:
        modal = self._modal()
        call = self._call(config, call_id)
        try:
            output = call.get(timeout=0)
        except modal.exception.OutputExpiredError as exc:
            raise AppException(f"Modal FunctionCall {call_id} output expired.") from exc
        except (TimeoutError, modal.exception.TimeoutError):
            # Modal documents TimeoutError from get(timeout=0) as the normal
            # "still running" signal. Depending on the SDK release this may
            # be the built-in TimeoutError or Modal's compatibility alias.
            return False, None
        except BaseException as exc:
            if self._is_cancelled_exception(exc):
                raise InterruptedError("Modal FunctionCall cancellation confirmed.") from exc
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            name = exc.__class__.__name__.lower()
            if any(term in name for term in ("connection", "service", "internal", "resourceexhausted")):
                raise ModalTransientTransportError(
                    f"Could not poll Modal FunctionCall {call_id}: {exc}"
                ) from exc
            raise AppException(f"Modal FunctionCall {call_id} failed: {exc}") from exc
        if not isinstance(output, dict):
            raise AppException("Modal FunctionCall returned an invalid pipeline result.")
        return True, output

    def cancel_call(
        self,
        config: ModalProviderConfig,
        *,
        call_id: str,
        timeout_seconds: int = 90,
    ) -> dict[str, Any]:
        """Cancel a Modal call with two hard-cancellation attempts.

        The first attempt terminates the containers immediately and waits up to
        50 seconds for Modal confirmation. If confirmation is unavailable, the
        same hard cancellation is sent again and checked for another 20
        seconds. Modal control-plane errors are logged but never prevent the
        retry or the final local cancellation result.
        """
        del timeout_seconds  # Kept for backward compatibility with existing callers.

        modal = self._modal()
        call = self._call(config, call_id)

        def request_hard_cancellation(attempt: int) -> None:
            try:
                call.cancel(terminate_containers=True)
            except BaseException as exc:
                if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                    raise
                # The call may already be cancelled/terminated or Modal's
                # control plane may be temporarily unavailable. In either
                # case, continue checking and allow the next attempt.
                logger.warning(
                    "Modal hard cancellation attempt %s failed for FunctionCall %s: %s",
                    attempt,
                    call_id,
                    exc,
                    exc_info=True,
                )

        def wait_for_confirmation(wait_seconds: int, attempt: int) -> dict[str, Any] | None:
            deadline = time.monotonic() + max(1, int(wait_seconds))
            while time.monotonic() < deadline:
                try:
                    graph = call.get_call_graph()
                    states = [self._graph_status_name(node) for node in graph]
                    if states and all(state in self._TERMINAL_GRAPH_STATES for state in states):
                        if "TERMINATED" in states:
                            return {
                                "status": "cancelled",
                                "confirmed": True,
                                "forced": False,
                                "attempts": attempt,
                                "call_id": call_id,
                                "states": states,
                            }
                        # Do not silently convert a genuinely completed or
                        # failed execution into a cancellation/refund.
                        raise AppException(
                            f"Modal FunctionCall {call_id} reached terminal state "
                            f"without TERMINATED: {states}"
                        )
                except AppException:
                    raise
                except BaseException as exc:
                    if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                        raise
                    if self._is_cancelled_exception(exc):
                        return {
                            "status": "cancelled",
                            "confirmed": True,
                            "forced": False,
                            "attempts": attempt,
                            "call_id": call_id,
                        }
                    logger.warning(
                        "Could not read Modal call graph while confirming cancellation "
                        "of FunctionCall %s (attempt %s): %s",
                        call_id,
                        attempt,
                        exc,
                    )

                try:
                    call.get(timeout=0)
                except (TimeoutError, modal.exception.TimeoutError):
                    time.sleep(0.5)
                    continue
                except BaseException as exc:
                    if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                        raise
                    if self._is_cancelled_exception(exc):
                        return {
                            "status": "cancelled",
                            "confirmed": True,
                            "forced": False,
                            "attempts": attempt,
                            "call_id": call_id,
                        }
                    # Transport/control-plane errors must not abort cancellation.
                    logger.warning(
                        "Could not query Modal FunctionCall %s while confirming "
                        "cancellation (attempt %s): %s",
                        call_id,
                        attempt,
                        exc,
                    )
                    time.sleep(0.5)
                    continue

                # A normal result means the call really completed before the
                # cancellation was confirmed. Preserve the previous protection
                # against incorrectly refunding a completed execution.
                raise AppException(
                    f"Modal FunctionCall {call_id} completed before cancellation "
                    "could be confirmed."
                )
            return None

        request_hard_cancellation(attempt=1)
        confirmed = wait_for_confirmation(wait_seconds=50, attempt=1)
        if confirmed is not None:
            return confirmed

        # Refresh the FunctionCall reference before retrying. If restoration
        # fails because Modal is temporarily unavailable, retain the original
        # handle and still perform the second attempt safely.
        try:
            call = self._call(config, call_id)
        except BaseException as exc:
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            logger.warning(
                "Could not refresh Modal FunctionCall %s before hard cancellation "
                "attempt 2; reusing the existing handle: %s",
                call_id,
                exc,
                exc_info=True,
            )

        request_hard_cancellation(attempt=2)
        confirmed = wait_for_confirmation(wait_seconds=20, attempt=2)
        if confirmed is not None:
            return confirmed

        logger.error(
            "Modal did not confirm cancellation of FunctionCall %s after two hard "
            "cancellation attempts (50s + 20s). Closing it locally as cancelled.",
            call_id,
        )
        return {
            "status": "cancelled",
            "confirmed": False,
            "forced": True,
            "attempts": 2,
            "call_id": call_id,
        }

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
                    "runtime_url": None,
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
