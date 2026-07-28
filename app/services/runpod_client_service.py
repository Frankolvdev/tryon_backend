import threading
from typing import Any

import httpx
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.common.enums import IntegrationProvider
from app.common.exceptions import ConflictException
from app.services.integration_service import integration_service


class RunPodClientService:
    def __init__(self) -> None:
        self._http_local = threading.local()

    def _client(self, timeout: float) -> httpx.Client:
        client = getattr(self._http_local, "client", None)
        current_timeout = getattr(self._http_local, "timeout", None)
        if client is None or current_timeout != float(timeout):
            if client is not None:
                client.close()
            client = httpx.Client(
                timeout=timeout,
                limits=httpx.Limits(
                    max_connections=20,
                    max_keepalive_connections=10,
                    keepalive_expiry=30.0,
                ),
            )
            self._http_local.client = client
            self._http_local.timeout = float(timeout)
        return client

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

        response = self._client(20.0).get(
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

        response = self._client(60.0).post(
                url,
                headers=self._headers(config.api_key),
                json=jsonable_encoder({"input": input_payload}),
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

        response = self._client(60.0).get(
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

        response = self._client(60.0).post(
                url,
                headers=self._headers(config.api_key),
            )

        response.raise_for_status()
        return response.json()


runpod_client_service = RunPodClientService()