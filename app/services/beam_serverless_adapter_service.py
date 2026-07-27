from __future__ import annotations

import time
from typing import Any, Callable

import requests
from sqlalchemy.orm import Session

from app.common.exceptions import AppException
from app.services.infrastructure_provider_service import infrastructure_provider_service


class BeamServerlessAdapterService:
    API_BASE = "https://api.beam.cloud/v2"

    @staticmethod
    def _headers(api_key: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    def health(self, db: Session) -> dict[str, Any]:
        cfg = infrastructure_provider_service.get_beam(db)
        return {"available": bool(cfg.enabled and cfg.api_key and cfg.endpoint), "endpoint": cfg.endpoint, "workspace": cfg.workspace}

    def submit_job(self, db: Session, *, input_data: dict[str, Any], endpoint: str | None = None) -> dict[str, Any]:
        cfg = infrastructure_provider_service.get_beam(db)
        target = str(endpoint or cfg.endpoint or "").strip()
        if not cfg.enabled or not cfg.api_key or not target:
            raise AppException("Beam is selected, but its API key or endpoint is not configured.")
        response = requests.post(target, headers=self._headers(cfg.api_key), json=input_data, timeout=min(cfg.timeout_seconds, 120))
        response.raise_for_status()
        data = response.json() if response.content else {}
        task_id = str(data.get("task_id") or data.get("id") or response.headers.get("X-Task-Id") or "").strip()
        if not task_id:
            raise AppException("Beam did not return a task ID. Use a Beam Task Queue endpoint for long-running generation jobs.")
        return {"provider_job_id": task_id, "endpoint": target, "status": str(data.get("status") or "PENDING")}

    def get_task(self, api_key: str, task_id: str, timeout: int = 30) -> dict[str, Any]:
        r=requests.get(f"{self.API_BASE}/task/{task_id}/", headers=self._headers(api_key), timeout=timeout)
        r.raise_for_status(); return r.json()

    def cancel_job(self, db: Session, *, provider_job_id: str, endpoint: str | None = None) -> dict[str, Any]:
        cfg=infrastructure_provider_service.get_beam(db)
        r=requests.delete(f"{self.API_BASE}/task/cancel/", headers=self._headers(cfg.api_key), json={"task_ids":[provider_job_id]}, timeout=30)
        r.raise_for_status(); return {"cancelled": True, "provider_job_id": provider_job_id}

    def execute_submitted_job(self, db: Session, *, provider_job_id: str, endpoint: str, timeout_seconds: int, progress_callback: Callable | None=None, cancellation_callback: Callable | None=None) -> dict[str, Any]:
        cfg=infrastructure_provider_service.get_beam(db); started=time.monotonic()
        while True:
            if cancellation_callback and cancellation_callback():
                self.cancel_job(db, provider_job_id=provider_job_id, endpoint=endpoint)
                raise InterruptedError("Beam task cancelled by user.")
            task=self.get_task(cfg.api_key, provider_job_id)
            status=str(task.get("status") or "PENDING").upper()
            if progress_callback:
                progress_callback(15 if status=="PENDING" else 55 if status=="RUNNING" else 95, f"Beam task status: {status}.", {"provider_status":status})
            if status=="COMPLETE":
                outputs=task.get("outputs")
                if isinstance(outputs,list) and len(outputs)==1: outputs=outputs[0]
                if outputs is None: outputs=task.get("output") or {}
                return {"provider":"beam", "provider_job_id":provider_job_id, "endpoint":endpoint, "output":outputs, "task":task, "execution_time_ms":int((time.monotonic()-started)*1000)}
            if status in {"FAILED","CANCELLED","TIMEOUT","EXPIRED"}:
                raise AppException(str(task.get("error") or f"Beam task ended with status {status}."))
            if time.monotonic()-started > timeout_seconds:
                raise TimeoutError(f"Beam task exceeded {timeout_seconds} seconds.")
            time.sleep(2)

beam_serverless_adapter_service = BeamServerlessAdapterService()
