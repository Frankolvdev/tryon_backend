from __future__ import annotations

import threading
from typing import Any


class BeamProgressService:
    _local = threading.local()
    _cancelled: set[str] = set()
    _lock = threading.RLock()

    @classmethod
    def bind_job(cls, job_id: str) -> None:
        cls._local.job_id = job_id

    @classmethod
    def unbind_job(cls) -> None:
        cls._local.job_id = None

    @classmethod
    def current_job_id(cls) -> str | None:
        return getattr(cls._local, "job_id", None)

    @classmethod
    def cancel(cls, job_id: str) -> None:
        with cls._lock:
            cls._cancelled.add(job_id)

    @classmethod
    def is_cancelled(cls) -> bool:
        job_id = cls.current_job_id()
        if not job_id:
            return False
        with cls._lock:
            return job_id in cls._cancelled

    @classmethod
    def clear(cls, job_id: str) -> None:
        with cls._lock:
            cls._cancelled.discard(job_id)

    @staticmethod
    def payload(**values: Any) -> dict[str, Any]:
        return values
