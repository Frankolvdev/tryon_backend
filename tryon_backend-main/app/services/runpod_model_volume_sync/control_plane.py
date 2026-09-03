from __future__ import annotations

import time
from typing import Any

import httpx


class RunPodModelSyncApiError(RuntimeError):
    pass


class RunPodModelSyncControlPlane:
    """REST client used only by model export to a RunPod Network Volume."""

    BASE_URL = "https://rest.runpod.io/v1"

    def __init__(self, api_key: str) -> None:
        self.api_key = str(api_key or "").strip()
        if not self.api_key:
            raise ValueError("Configura la API key de RunPod antes de exportar modelos.")

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def request(self, method: str, path: str, *, timeout: int = 60, retries: int = 2,
                payload: dict[str, Any] | None = None) -> Any:
        url = f"{self.BASE_URL}/{path.lstrip('/')}"
        last_detail = ""
        for attempt in range(retries + 1):
            try:
                with httpx.Client(timeout=float(timeout)) as client:
                    response = client.request(method, url, headers=self.headers, json=payload)
            except httpx.HTTPError as exc:
                last_detail = str(exc)
                if attempt >= retries:
                    raise RunPodModelSyncApiError(f"No fue posible conectar con RunPod REST: {exc}") from exc
                time.sleep(min(2 ** attempt, 4))
                continue
            if response.is_success:
                if response.status_code == 204 or not response.content:
                    return None
                try:
                    return response.json()
                except ValueError as exc:
                    raise RunPodModelSyncApiError("RunPod devolvió una respuesta no JSON.") from exc
            detail = (response.text or "<sin cuerpo>").strip()
            last_detail = detail[-2000:]
            if response.status_code < 500 or attempt >= retries:
                raise RunPodModelSyncApiError(
                    f"RunPod REST {method.upper()} {path} respondió HTTP {response.status_code}: {last_detail}"
                )
            time.sleep(min(2 ** attempt, 4))
        raise RunPodModelSyncApiError(last_detail or "RunPod no respondió.")

    def get_volume(self, volume_id: str) -> dict[str, Any]:
        return self.request("GET", f"networkvolumes/{volume_id}", retries=1)

    def create_pod(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.request("POST", "pods", payload=payload, retries=2)

    def get_pod(self, pod_id: str) -> dict[str, Any]:
        return self.request("GET", f"pods/{pod_id}", retries=1)

    def delete_pod(self, pod_id: str) -> None:
        if not str(pod_id or "").strip():
            return
        self.request("DELETE", f"pods/{pod_id}", retries=3)
