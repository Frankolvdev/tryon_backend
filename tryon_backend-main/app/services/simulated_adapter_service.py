import time
from typing import Any
from uuid import uuid4


class SimulatedAdapterService:
    """Deterministic no-GPU adapter used by development and test flows.

    This foundation intentionally does not persist or dispatch jobs yet. It
    exposes the same provider-oriented primitives that the worker integration
    will consume in the next increment.
    """

    provider = "simulated"

    def health(self) -> dict[str, Any]:
        return {
            "available": True,
            "provider": self.provider,
            "mode": "simulation",
        }

    def submit_job(
        self,
        *,
        input_data: dict[str, Any],
        delay_seconds: float = 0.0,
    ) -> dict[str, Any]:
        provider_job_id = f"sim_{uuid4().hex}"

        return {
            "provider": self.provider,
            "provider_job_id": provider_job_id,
            "status": "IN_QUEUE",
            "input": input_data,
            "delay_seconds": max(float(delay_seconds), 0.0),
            "submitted_at": time.time(),
        }

    def execute_job(
        self,
        *,
        provider_job_id: str,
        input_data: dict[str, Any],
        delay_seconds: float = 0.0,
    ) -> dict[str, Any]:
        resolved_delay = max(float(delay_seconds), 0.0)

        if resolved_delay:
            time.sleep(resolved_delay)

        return {
            "provider": self.provider,
            "provider_job_id": provider_job_id,
            "status": "COMPLETED",
            "output": {
                "simulated": True,
                "message": "Simulated AI execution completed.",
                "input": input_data,
            },
        }

    def cancel_job(
        self,
        *,
        provider_job_id: str,
    ) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "provider_job_id": provider_job_id,
            "status": "CANCELLED",
        }


simulated_adapter_service = SimulatedAdapterService()
