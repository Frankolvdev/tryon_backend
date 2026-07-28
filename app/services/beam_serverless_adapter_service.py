from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

import requests
from requests.adapters import HTTPAdapter
from sqlalchemy.orm import Session

from app.common.exceptions import AppException
from app.services.infrastructure_provider_service import infrastructure_provider_service
from app.services.beam_credentials_service import beam_credentials_service

logger = logging.getLogger(__name__)


class BeamServerlessAdapterService:
    """Beam adapter with per-thread pooled sessions, isolated from Modal/RunPod."""

    API_BASE = "https://api.beam.cloud/v2"

    def __init__(self) -> None:
        self._session_local = threading.local()

    @staticmethod
    def _headers(api_key: str) -> dict[str, str]:
        token = beam_credentials_service.normalize_token(api_key)
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    @staticmethod
    def _normalize_endpoint(endpoint: str) -> str:
        target = str(endpoint or "").strip().rstrip("/")
        if not target:
            return ""
        if not target.startswith(("https://", "http://")):
            raise AppException("Beam endpoint must be an absolute HTTP or HTTPS URL.")
        return target

    @staticmethod
    def _task_output(task: dict[str, Any]) -> Any:
        outputs = task.get("outputs")
        if isinstance(outputs, list) and len(outputs) == 1:
            return outputs[0]
        if outputs is not None:
            return outputs
        return task.get("output") or {}

    def _new_session(self) -> requests.Session:
        session = requests.Session()
        adapter = HTTPAdapter(pool_connections=10, pool_maxsize=20, max_retries=0, pool_block=True)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def _session(self) -> requests.Session:
        session = getattr(self._session_local, "session", None)
        if session is None:
            session = self._new_session()
            self._session_local.session = session
        return session

    def _reset_session(self) -> None:
        session = getattr(self._session_local, "session", None)
        if session is not None:
            try:
                session.close()
            except Exception:
                logger.debug("Could not close failed Beam session.", exc_info=True)
        self._session_local.session = None

    @staticmethod
    def _is_transient_transport_error(error: BaseException) -> bool:
        if isinstance(error, (requests.ConnectionError, requests.Timeout)):
            return True
        winerror = getattr(error, "winerror", None)
        if winerror in {10054, 10055, 10060, 10061}:
            return True
        cause = getattr(error, "__cause__", None)
        return bool(cause and cause is not error and BeamServerlessAdapterService._is_transient_transport_error(cause))

    def health(self, db: Session) -> dict[str, Any]:
        cfg = infrastructure_provider_service.get_beam(db)
        return {
            "available": bool(cfg.enabled and cfg.api_key and cfg.endpoint),
            "endpoint": cfg.endpoint,
            "workspace": cfg.workspace,
        }

    def submit_job(self, db: Session, *, input_data: dict[str, Any], endpoint: str | None = None) -> dict[str, Any]:
        cfg = infrastructure_provider_service.get_beam(db)
        target = self._normalize_endpoint(endpoint or cfg.endpoint or "")
        if not cfg.enabled or not cfg.api_key or not target:
            raise AppException("Beam is selected, but its API key or endpoint is not configured.")
        # Deliberately no automatic retry: replaying submission could duplicate a paid job.
        response = self._session().post(
            target,
            headers=self._headers(cfg.api_key),
            json=input_data,
            timeout=min(cfg.timeout_seconds, 120),
        )
        response.raise_for_status()
        data = response.json() if response.content else {}
        task_id = str(data.get("task_id") or data.get("id") or response.headers.get("X-Task-Id") or "").strip()
        if not task_id:
            raise AppException("Beam did not return a task ID. Use a Beam Task Queue endpoint for long-running generation jobs.")
        return {"provider_job_id": task_id, "endpoint": target, "status": str(data.get("status") or "PENDING")}

    def get_task(
        self,
        api_key: str,
        task_id: str,
        timeout: int = 30,
        session: requests.Session | None = None,
    ) -> dict[str, Any]:
        active_session = session or self._session()
        response = active_session.get(
            f"{self.API_BASE}/task/{task_id}/",
            headers=self._headers(api_key),
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()

    def cancel_job(self, db: Session, *, provider_job_id: str, endpoint: str | None = None) -> dict[str, Any]:
        del endpoint
        cfg = infrastructure_provider_service.get_beam(db)
        response = self._session().delete(
            f"{self.API_BASE}/task/cancel/",
            headers=self._headers(cfg.api_key),
            json={"task_ids": [provider_job_id]},
            timeout=30,
        )
        response.raise_for_status()
        return {"cancelled": True, "provider_job_id": provider_job_id}

    def execute_submitted_job(
        self,
        db: Session,
        *,
        provider_job_id: str,
        endpoint: str,
        timeout_seconds: int,
        progress_callback: Callable | None = None,
        cancellation_callback: Callable | None = None,
    ) -> dict[str, Any]:
        cfg = infrastructure_provider_service.get_beam(db)
        started = time.monotonic()
        polling_interval = 2.0
        active_session = self._session()
        transient_failures = 0

        while True:
            if cancellation_callback and cancellation_callback():
                self.cancel_job(db, provider_job_id=provider_job_id, endpoint=endpoint)
                raise InterruptedError("Beam task cancelled by user.")

            try:
                task = self.get_task(
                    cfg.api_key,
                    provider_job_id,
                    session=active_session,
                )
                transient_failures = 0
            except Exception as error:
                if not self._is_transient_transport_error(error):
                    raise
                transient_failures += 1
                logger.warning(
                    "Transient Beam status transport error; preserving task and retrying: "
                    "task_id=%s attempt=%s error=%s",
                    provider_job_id,
                    transient_failures,
                    error,
                )
                self._reset_session()
                active_session = self._session()
                time.sleep(min(8.0, polling_interval * transient_failures))
                continue

            status = str(task.get("status") or "PENDING").upper()
            if progress_callback:
                progress_callback(
                    15 if status == "PENDING" else 55 if status == "RUNNING" else 95,
                    f"Beam task status: {status}.",
                    {"provider_status": status},
                )
            if status == "COMPLETE":
                outputs = self._task_output(task)
                return {
                    "provider": "beam",
                    "provider_job_id": provider_job_id,
                    "endpoint": endpoint,
                    "output": outputs,
                    "task": task,
                    "execution_time_ms": int((time.monotonic() - started) * 1000),
                }
            if status in {"FAILED", "CANCELLED", "TIMEOUT", "EXPIRED"}:
                raise AppException(str(task.get("error") or f"Beam task ended with status {status}."))
            if time.monotonic() - started > timeout_seconds:
                raise TimeoutError(f"Beam task exceeded {timeout_seconds} seconds.")

            time.sleep(polling_interval)
            polling_interval = min(6.0, polling_interval + 0.5)

    def submit_pipeline(self, db: Session, *, payload: dict[str, Any], endpoint: str | None = None) -> str:
        """Beam equivalent of Modal ``spawn``: enqueue and return a persistent task ID."""
        submitted = self.submit_job(db, input_data=payload, endpoint=endpoint)
        return str(submitted["provider_job_id"])

    def poll_result(self, db: Session, *, task_id: str) -> tuple[bool, dict[str, Any] | None]:
        """Beam equivalent of ``FunctionCall.from_id(...).get(timeout=0)``."""
        cfg = infrastructure_provider_service.get_beam(db)
        task = self.get_task(cfg.api_key, task_id)
        status = str(task.get("status") or "PENDING").upper()
        if status in {"PENDING", "RUNNING", "RETRY", "QUEUED"}:
            return False, None
        if status == "COMPLETE":
            output = self._task_output(task)
            if not isinstance(output, dict):
                raise AppException("Beam task returned an invalid pipeline result.")
            return True, output
        if status == "CANCELLED":
            raise InterruptedError("Beam task cancellation confirmed.")
        raise AppException(str(task.get("error") or f"Beam task ended with status {status}."))

    def cancel_task(self, db: Session, *, task_id: str) -> dict[str, Any]:
        """Beam equivalent of ``FunctionCall.cancel``."""
        return self.cancel_job(db, provider_job_id=task_id)


beam_serverless_adapter_service = BeamServerlessAdapterService()
