from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.common.enums import IntegrationProvider
from app.common.exceptions import ConflictException
from app.services.integration_service import integration_service


class RunPodClientService:
    def _get_config(self, db: Session):
        config = integration_service.get_config(db, IntegrationProvider.RUNPOD)

        if not config.is_enabled:
            raise ConflictException("RunPod integration is disabled.")

        if not config.api_key:
            raise ConflictException("RunPod API key is not configured.")

        return config

    def _headers(self, api_key: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def health_check(self, db: Session) -> dict[str, Any]:
        config = self._get_config(db)

        with httpx.Client(timeout=20.0) as client:
            response = client.get(
                "https://api.runpod.ai/v2/user",
                headers=self._headers(config.api_key),
            )

        response.raise_for_status()

        return {
            "healthy": True,
            "status_code": response.status_code,
            "response": response.json(),
        }

    def submit_job(
        self,
        db: Session,
        *,
        endpoint_id: str,
        input_payload: dict[str, Any],
    ) -> dict[str, Any]:
        config = self._get_config(db)

        url = f"https://api.runpod.ai/v2/{endpoint_id}/run"

        with httpx.Client(timeout=60.0) as client:
            response = client.post(
                url,
                headers=self._headers(config.api_key),
                json={"input": input_payload},
            )

        response.raise_for_status()
        return response.json()

    def get_status(
        self,
        db: Session,
        *,
        endpoint_id: str,
        provider_job_id: str,
    ) -> dict[str, Any]:
        config = self._get_config(db)

        url = f"https://api.runpod.ai/v2/{endpoint_id}/status/{provider_job_id}"

        with httpx.Client(timeout=60.0) as client:
            response = client.get(
                url,
                headers=self._headers(config.api_key),
            )

        response.raise_for_status()
        return response.json()

    def cancel_job(
        self,
        db: Session,
        *,
        endpoint_id: str,
        provider_job_id: str,
    ) -> dict[str, Any]:
        config = self._get_config(db)

        url = f"https://api.runpod.ai/v2/{endpoint_id}/cancel/{provider_job_id}"

        with httpx.Client(timeout=60.0) as client:
            response = client.post(
                url,
                headers=self._headers(config.api_key),
            )

        response.raise_for_status()
        return response.json()


runpod_client_service = RunPodClientService()