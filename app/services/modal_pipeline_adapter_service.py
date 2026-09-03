from __future__ import annotations

import asyncio
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
        self._calls_lock = threading.Lock()
        self._calls: dict[str, Any] = {}
        self._cancellation_locks_lock = threading.Lock()
        self._cancellation_locks: dict[str, threading.Lock] = {}
        self._cancellation_results: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _modal() -> Any:
        try:
            import modal
        except ImportError as exc:
            raise AppException(
                "Modal Python SDK is not installed in the Backend environment."
            ) from exc
        return modal

    @staticmethod
    def _credential_key(config: ModalProviderConfig) -> tuple[str, str]:
        token_id = str(config.token_id or "").strip()
        token_secret = str(config.token_secret or "").strip()
        if not token_id or not token_secret:
            raise AppException("Modal credentials are not configured.")
        return token_id, token_secret

    def _cached_client(self, key: tuple[str, str]) -> Any | None:
        with self._client_lock:
            client = self._clients.get(key)
            if client is not None and not bool(getattr(client, "is_closed", lambda: False)()):
                return client
            if client is not None:
                self._clients.pop(key, None)
            return None

    def _client(self, config: ModalProviderConfig) -> Any:
        """Return a Modal client for synchronous adapter entry points only."""
        token_id, token_secret = self._credential_key(config)
        key = (token_id, token_secret)
        client = self._cached_client(key)
        if client is not None:
            return client

        client = self._modal().Client.from_credentials(token_id, token_secret)
        with self._client_lock:
            current = self._clients.get(key)
            if current is not None and not bool(getattr(current, "is_closed", lambda: False)()):
                return current
            self._clients[key] = client
            return client

    async def _client_async(self, config: ModalProviderConfig) -> Any:
        """Return a Modal client without invoking a blocking SDK interface in asyncio."""
        token_id, token_secret = self._credential_key(config)
        key = (token_id, token_secret)
        client = self._cached_client(key)
        if client is not None:
            return client

        # Modal's Client.from_credentials opens the authenticated connection and is
        # therefore an I/O operation. In async supervision it must use the SDK's
        # asynchronous interface; otherwise Modal emits AsyncUsageWarning and the
        # event loop can be blocked during client creation.
        client = await self._modal().Client.from_credentials.aio(token_id, token_secret)
        with self._client_lock:
            current = self._clients.get(key)
            if current is not None and not bool(getattr(current, "is_closed", lambda: False)()):
                return current
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

    def _call(self, config: ModalProviderConfig, call_id: str, *, refresh: bool = False) -> Any:
        call_id = str(call_id or "").strip()
        if not call_id:
            raise AppException("Modal FunctionCall ID is missing.")
        if not refresh:
            with self._calls_lock:
                original = self._calls.get(call_id)
            if original is not None:
                return original
        try:
            restored = self._modal().FunctionCall.from_id(
                call_id, client=self._client(config)
            )
        except Exception as exc:
            raise AppException(f"Could not restore Modal FunctionCall {call_id}: {exc}") from exc
        with self._calls_lock:
            self._calls[call_id] = restored
        return restored

    async def _call_async(
        self,
        config: ModalProviderConfig,
        call_id: str,
        *,
        refresh: bool = False,
    ) -> Any:
        """Restore a durable FunctionCall using an async-safe Modal client path."""
        call_id = str(call_id or "").strip()
        if not call_id:
            raise AppException("Modal FunctionCall ID is missing.")
        if not refresh:
            with self._calls_lock:
                original = self._calls.get(call_id)
            if original is not None:
                return original
        try:
            client = await self._client_async(config)
            # FunctionCall.from_id() is intentionally synchronous in current Modal:
            # it only creates a lazy handle and performs no network I/O.
            restored = self._modal().FunctionCall.from_id(call_id, client=client)
        except Exception as exc:
            raise AppException(f"Could not restore Modal FunctionCall {call_id}: {exc}") from exc
        with self._calls_lock:
            self._calls[call_id] = restored
        return restored

    def _cancellation_lock(self, call_id: str) -> threading.Lock:
        with self._cancellation_locks_lock:
            lock = self._cancellation_locks.get(call_id)
            if lock is None:
                lock = threading.Lock()
                self._cancellation_locks[call_id] = lock
            return lock

    def _forget_call(self, call_id: str) -> None:
        with self._calls_lock:
            self._calls.pop(call_id, None)

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

    async def _call_graph_states_async(self, call: Any) -> list[str]:
        """Read Modal's durable call graph without blocking the asyncio supervisor."""
        getter = getattr(call, "get_call_graph", None)
        if getter is None:
            return []
        aio_getter = getattr(getter, "aio", None)
        if callable(aio_getter):
            graph = await aio_getter()
        else:
            graph = await asyncio.to_thread(getter)
        return [self._graph_status_name(node) for node in (graph or [])]

    @staticmethod
    async def _cancel_local_wait_task(task: asyncio.Task[Any]) -> None:
        """Stop only the local SDK wait; never cancel the provider FunctionCall."""
        if task.done():
            return
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass

    def submit_pipeline(self, config: ModalProviderConfig, *, payload: dict[str, Any]) -> str:
        execution_id = str(payload.get("execution_id") or "")
        sdk_version = str(getattr(self._modal(), "__version__", "unknown"))
        logger.warning(
            "[backend-modal-spawn-start] execution_id=%s app_name=%s environment=%s sdk_version=%s",
            execution_id,
            str(config.app_name or "").strip(),
            str(config.environment or "main").strip() or "main",
            sdk_version,
        )
        try:
            worker = self._worker(config)
            # Apply the current global scaledown to the already deployed runtime.
            # This changes future container lifecycle without creating a separate pool.
            try:
                from app.db.database import SessionLocal
                from app.services.ai_engine_settings_service import ai_engine_settings_service
                with SessionLocal() as db:
                    scaledown = int(ai_engine_settings_service.get(db).modal_scaledown_window_seconds)
                worker.run_pipeline.update_autoscaler(scaledown_window=scaledown)
                logger.info("[backend-modal-autoscaler] scaledown_window=%s", scaledown)
            except Exception as autoscaler_exc:
                logger.warning("[backend-modal-autoscaler-warning] %s", autoscaler_exc)
            call = worker.run_pipeline.spawn(jsonable_encoder(payload))
        except Exception as exc:
            raise AppException(f"Could not submit the Modal FunctionCall: {exc}") from exc
        call_id = str(getattr(call, "object_id", "") or "").strip()
        if not call_id:
            raise AppException("Modal did not return a FunctionCall ID.")
        with self._calls_lock:
            self._calls[call_id] = call
        logger.warning(
            "[backend-modal-spawn-created] execution_id=%s call_id=%s sdk_version=%s",
            execution_id,
            call_id,
            sdk_version,
        )
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

    async def await_result_async(
        self,
        config: ModalProviderConfig,
        *,
        call_id: str,
        timeout_seconds: int,
    ) -> dict[str, Any]:
        """Wait for one durable Modal FunctionCall without per-job status polling.

        Normal completion is event-driven through Modal ``FunctionCall.get.aio``.
        A transient control-plane reconnect may reattach to the SAME persisted
        FunctionCall ID, but this method never submits, spawns, requeues, or retries
        the remote generation itself.
        """
        modal = self._modal()
        call_id = str(call_id or "").strip()
        if not call_id:
            raise AppException("Modal FunctionCall ID is missing.")

        started = time.monotonic()
        deadline = started + max(1.0, float(timeout_seconds))
        transient_attempts = 0

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(
                    f"Modal FunctionCall {call_id} exceeded {timeout_seconds} seconds."
                )

            call = await self._call_async(
                config,
                call_id,
                refresh=transient_attempts > 0,
            )
            try:
                output = await call.get.aio(timeout=remaining)
            except modal.exception.OutputExpiredError as exc:
                raise AppException(
                    f"Modal FunctionCall {call_id} output expired."
                ) from exc
            except (TimeoutError, modal.exception.TimeoutError) as exc:
                # This is the full execution deadline, not a polling interval.
                raise TimeoutError(
                    f"Modal FunctionCall {call_id} exceeded {timeout_seconds} seconds."
                ) from exc
            except asyncio.CancelledError:
                # Backend shutdown only. The provider call is left untouched so
                # startup recovery can reattach to the same durable FunctionCall ID.
                raise
            except BaseException as exc:
                if self._is_cancelled_exception(exc):
                    raise InterruptedError(
                        "Modal FunctionCall cancellation confirmed."
                    ) from exc
                if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                    raise
                name = exc.__class__.__name__.lower()
                if any(
                    term in name
                    for term in (
                        "connection",
                        "service",
                        "internal",
                        "resourceexhausted",
                        "unavailable",
                    )
                ):
                    # Reconnect only to the SAME call_id. This is transport recovery,
                    # never a second Modal generation / spawn.
                    transient_attempts += 1
                    await asyncio.sleep(min(10.0, 0.5 * transient_attempts))
                    continue
                raise AppException(
                    f"Modal FunctionCall {call_id} failed: {exc}"
                ) from exc

            if not isinstance(output, dict):
                raise AppException(
                    "Modal FunctionCall returned an invalid pipeline result."
                )

            self._forget_call(call_id)
            return {
                "provider": "modal",
                "output": output,
                "execution_time_ms": int((time.monotonic() - started) * 1000),
                "runtime_url": None,
                "provider_job_id": call_id,
                "resumed": transient_attempts > 0,
            }

    async def inspect_terminal_failure_async(
        self,
        config: ModalProviderConfig,
        *,
        call_id: str,
    ) -> dict[str, Any] | None:
        """Low-frequency safety inspection for a durable Modal call.

        This is intentionally NOT part of normal result delivery. The global
        reconciler calls it at a coarse interval to catch container/init failures
        that can leave the parent FunctionCall pending while Modal tries another
        container. No new FunctionCall is ever created here.
        """
        call_id = str(call_id or "").strip()
        if not call_id:
            return None
        call = await self._call_async(config, call_id)
        getter = getattr(call, "get_call_graph", None)
        if not callable(getter):
            return None
        try:
            aio_getter = getattr(getter, "aio", None)
            if callable(aio_getter):
                graph = await aio_getter()
            else:
                graph = await asyncio.to_thread(getter)
        except BaseException as exc:
            if isinstance(exc, (KeyboardInterrupt, SystemExit, asyncio.CancelledError)):
                raise
            logger.warning(
                "Could not inspect Modal call graph: call_id=%s error=%s",
                call_id,
                exc,
            )
            return None

        states = [self._graph_status_name(node) for node in list(graph or [])]
        failed = [
            state
            for state in states
            if state in {"FAILURE", "INIT_FAILURE", "TIMEOUT"}
        ]
        if not failed:
            return None
        all_terminal = bool(states) and all(
            state in self._TERMINAL_GRAPH_STATES for state in states
        )
        return {
            "call_id": call_id,
            "states": states,
            "failed_states": failed,
            "all_terminal": all_terminal,
        }

    async def stop_failed_call_async(
        self,
        config: ModalProviderConfig,
        *,
        call_id: str,
    ) -> None:
        """Stop the SAME pending FunctionCall after a child/init failure.

        This prevents Modal from continuing to provision replacement containers.
        It never submits, spawns, or requeues work.
        """
        call = await self._call_async(config, call_id)
        cancel = getattr(call, "cancel", None)
        if not callable(cancel):
            return
        try:
            aio_cancel = getattr(cancel, "aio", None)
            if callable(aio_cancel):
                await aio_cancel(terminate_containers=False)
            else:
                await asyncio.to_thread(cancel, terminate_containers=False)
        finally:
            self._forget_call(call_id)

    def cancel_call(
        self,
        config: ModalProviderConfig,
        *,
        call_id: str,
        timeout_seconds: int = 90,
    ) -> dict[str, Any]:
        """Cancel a Modal call and preserve the existing 50s + 20s waits."""
        del timeout_seconds  # Kept for backward compatibility with existing callers.

        call_id = str(call_id or "").strip()
        if not call_id:
            raise AppException("Modal FunctionCall ID is missing.")

        # The endpoint and the execution worker can observe cancellation at the
        # same time. Only one of them may drive the 50s + 20s protocol.
        with self._cancellation_lock(call_id):
            cached_result = self._cancellation_results.get(call_id)
            if cached_result is not None:
                return dict(cached_result)

            modal = self._modal()
            sdk_version = str(getattr(modal, "__version__", "unknown"))
            call = self._call(config, call_id)
            errors: list[dict[str, str | int]] = []

            logger.warning(
                "[backend-modal-cancel-start] call_id=%s sdk_version=%s terminate_containers=false waits=50s+20s",
                call_id,
                sdk_version,
            )

            def request_hard_cancellation(attempt: int) -> bool:
                try:
                    call.cancel(terminate_containers=False)
                    logger.warning(
                        "[backend-modal-cancel-sent] call_id=%s attempt=%s",
                        call_id,
                        attempt,
                    )
                    return True
                except BaseException as exc:
                    if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                        raise
                    errors.append({
                        "attempt": attempt,
                        "type": exc.__class__.__name__,
                        "message": str(exc),
                    })
                    logger.exception(
                        "[backend-modal-cancel-error] request failed before confirmation: "
                        "call_id=%s attempt=%s sdk_version=%s",
                        call_id,
                        attempt,
                        sdk_version,
                    )
                    return False

            def confirmed_result(attempt: int, states: list[str] | None = None) -> dict[str, Any]:
                self._forget_call(call_id)
                result: dict[str, Any] = {
                    "status": "cancelled",
                    "confirmed": True,
                    "forced": False,
                    "attempts": attempt,
                    "call_id": call_id,
                    "sdk_version": sdk_version,
                    "errors": errors,
                }
                if states is not None:
                    result["states"] = states
                self._cancellation_results[call_id] = dict(result)
                return result

            def wait_for_confirmation(wait_seconds: int, attempt: int) -> dict[str, Any] | None:
                deadline = time.monotonic() + max(1, int(wait_seconds))
                while time.monotonic() < deadline:
                    try:
                        graph = call.get_call_graph()
                        states = [self._graph_status_name(node) for node in graph]
                        if states and all(state in self._TERMINAL_GRAPH_STATES for state in states):
                            if "TERMINATED" in states:
                                logger.warning(
                                    "Modal cancellation confirmed by call graph: "
                                    "call_id=%s attempt=%s states=%s",
                                    call_id,
                                    attempt,
                                    states,
                                )
                                return confirmed_result(attempt, states)
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
                            logger.warning(
                                "Modal cancellation confirmed by call-graph exception: "
                                "call_id=%s attempt=%s exception=%s",
                                call_id,
                                attempt,
                                exc,
                            )
                            return confirmed_result(attempt)
                        logger.warning(
                            "Could not read Modal call graph while confirming cancellation: "
                            "call_id=%s attempt=%s error=%s",
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
                            logger.warning(
                                "Modal cancellation confirmed by result exception: "
                                "call_id=%s attempt=%s exception=%s",
                                call_id,
                                attempt,
                                exc,
                            )
                            return confirmed_result(attempt)
                        logger.warning(
                            "Could not query Modal FunctionCall while confirming cancellation: "
                            "call_id=%s attempt=%s error=%s",
                            call_id,
                            attempt,
                            exc,
                        )
                        time.sleep(0.5)
                        continue

                    raise AppException(
                        f"Modal FunctionCall {call_id} completed before cancellation "
                        "could be confirmed."
                    )
                return None

            sent_attempt_1 = request_hard_cancellation(attempt=1)
            confirmed = wait_for_confirmation(wait_seconds=50, attempt=1)
            if confirmed is not None:
                confirmed["request_sent"] = sent_attempt_1
                return confirmed

            # Refresh only for the second attempt. The original spawn handle is
            # preferred for attempt 1; from_id() is the recovery path.
            try:
                call = self._call(config, call_id, refresh=True)
            except BaseException as exc:
                if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                    raise
                errors.append({
                    "attempt": 2,
                    "type": exc.__class__.__name__,
                    "message": f"FunctionCall refresh failed: {exc}",
                })
                logger.exception(
                    "Could not refresh Modal FunctionCall before attempt 2; "
                    "reusing existing handle: call_id=%s",
                    call_id,
                )

            sent_attempt_2 = request_hard_cancellation(attempt=2)
            confirmed = wait_for_confirmation(wait_seconds=20, attempt=2)
            if confirmed is not None:
                confirmed["request_sent"] = sent_attempt_1 or sent_attempt_2
                return confirmed

            request_sent = sent_attempt_1 or sent_attempt_2
            logger.error(
                "[backend-modal-cancel-unconfirmed] Modal did not confirm cancellation after 50s + 20s: "
                "call_id=%s request_sent=%s errors=%s",
                call_id,
                request_sent,
                errors,
            )
            result = {
                "status": "cancel_requested_unconfirmed" if request_sent else "cancel_failed",
                "confirmed": False,
                "forced": False,
                "request_sent": request_sent,
                "attempts": 2,
                "call_id": call_id,
                "sdk_version": sdk_version,
                "errors": errors,
            }
            self._cancellation_results[call_id] = dict(result)
            return result

    def execute_pipeline(
        self,
        config: ModalProviderConfig,
        *,
        payload: dict[str, Any],
        timeout_seconds: int,
        progress_callback: Callable[[float, str, dict[str, Any] | None], None] | None = None,
        cancellation_callback: Callable[[], bool] | None = None,
        submitted_callback: Callable[[str], None] | None = None,
        existing_call_id: str | None = None,
    ) -> dict[str, Any]:
        if cancellation_callback and cancellation_callback():
            raise InterruptedError("Modal execution cancelled before dispatch.")
        if progress_callback:
            progress_callback(2.0, "Submitting Modal FunctionCall.", {"provider_status": "DISPATCHING"})
        started = time.monotonic()
        call_id = str(existing_call_id or "").strip()
        resumed = bool(call_id)
        if resumed:
            self._call(config, call_id, refresh=True)
            logger.warning("[backend-modal-resume] execution_id=%s call_id=%s", payload.get("execution_id"), call_id)
        else:
            call_id = self.submit_pipeline(config, payload=payload)
            if submitted_callback:
                submitted_callback(call_id)
        if cancellation_callback and cancellation_callback():
            cancellation = self.cancel_call(config, call_id=call_id)
            raise InterruptedError(
                f"Modal execution cancellation handled immediately after dispatch: {cancellation}"
            )
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
            if cancellation_callback and cancellation_callback():
                cancellation = self.cancel_call(config, call_id=call_id)
                raise InterruptedError(
                    f"Modal execution cancellation handled by worker: {cancellation}"
                )
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
                    "resumed": resumed,
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
