from __future__ import annotations

import time
from typing import Any

import httpx


class RunPodControlPlaneError(RuntimeError):
    """RunPod REST failure with a safe, actionable response excerpt."""

    def __init__(self, *, method: str, url: str, status_code: int, response_text: str):
        body = (response_text or "").strip()
        if len(body) > 2000:
            body = body[:2000] + "..."
        super().__init__(
            f"RunPod REST {method.upper()} {url} respondió HTTP {status_code}. "
            f"Respuesta: {body or '<sin cuerpo>'}"
        )
        self.method = method.upper()
        self.url = url
        self.status_code = status_code
        self.response_text = body


class RunPodControlPlaneService:
    """Cliente aislado del REST API de RunPod para recursos de infraestructura.

    La API de ejecución de jobs vive en api.runpod.ai/v2; la administración de
    templates, endpoints y network volumes vive en rest.runpod.io/v1.
    """

    BASE_URL = "https://rest.runpod.io/v1"

    @staticmethod
    def _headers(api_key: str) -> dict[str, str]:
        if not api_key.strip():
            raise ValueError("Configura la API key de RunPod.")
        return {
            "Authorization": f"Bearer {api_key.strip()}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _safe_json(response: httpx.Response) -> Any:
        if response.status_code == 204 or not response.content:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise RunPodControlPlaneError(
                method=response.request.method,
                url=str(response.request.url),
                status_code=response.status_code,
                response_text=response.text or "RunPod devolvió una respuesta no JSON.",
            ) from exc

    def request(
        self,
        method: str,
        path: str,
        *,
        api_key: str,
        timeout_seconds: int = 60,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        retry_server_errors: int = 0,
    ) -> Any:
        url = f"{self.BASE_URL}/{path.lstrip('/')}"
        attempts = max(1, int(retry_server_errors) + 1)
        last_response: httpx.Response | None = None

        for attempt in range(1, attempts + 1):
            with httpx.Client(timeout=float(timeout_seconds)) as client:
                response = client.request(
                    method,
                    url,
                    headers=self._headers(api_key),
                    json=json,
                    params=params,
                )
            last_response = response
            if response.is_success:
                return self._safe_json(response)
            if response.status_code < 500 or attempt >= attempts:
                raise RunPodControlPlaneError(
                    method=method,
                    url=url,
                    status_code=response.status_code,
                    response_text=response.text,
                )
            time.sleep(min(2 ** (attempt - 1), 4))

        # Defensive only; the loop either returns or raises.
        raise RunPodControlPlaneError(
            method=method,
            url=url,
            status_code=last_response.status_code if last_response else 500,
            response_text=last_response.text if last_response else "Sin respuesta de RunPod.",
        )


    def create_pod(self, *, api_key: str, payload: dict[str, Any], timeout_seconds: int = 60) -> dict[str, Any]:
        return self.request(
            "POST", "pods", api_key=api_key, timeout_seconds=timeout_seconds,
            json=payload, retry_server_errors=2,
        )

    def get_pod(self, pod_id: str, *, api_key: str, timeout_seconds: int = 60) -> dict[str, Any]:
        return self.request("GET", f"pods/{pod_id}", api_key=api_key, timeout_seconds=timeout_seconds)

    def delete_pod(self, pod_id: str, *, api_key: str, timeout_seconds: int = 60) -> Any:
        if not str(pod_id or "").strip():
            raise ValueError("Se requiere el ID del Pod temporal para eliminarlo.")
        return self.request("DELETE", f"pods/{pod_id}", api_key=api_key, timeout_seconds=timeout_seconds)

    def account_probe(self, *, api_key: str, timeout_seconds: int = 30) -> dict[str, Any]:
        endpoints = self.request("GET", "endpoints", api_key=api_key, timeout_seconds=timeout_seconds)
        return {"endpoint_count": len(endpoints or [])}

    def list_endpoints(self, *, api_key: str, timeout_seconds: int = 60) -> list[dict[str, Any]]:
        return self.request("GET", "endpoints", api_key=api_key, timeout_seconds=timeout_seconds) or []

    def find_endpoint_by_name(self, name: str, *, api_key: str, timeout_seconds: int = 60) -> dict[str, Any] | None:
        expected = str(name or "").strip()
        if not expected:
            return None
        return next(
            (item for item in self.list_endpoints(api_key=api_key, timeout_seconds=timeout_seconds)
             if str(item.get("name") or "").strip() == expected),
            None,
        )

    def list_network_volumes(self, *, api_key: str, timeout_seconds: int = 60) -> list[dict[str, Any]]:
        return self.request("GET", "networkvolumes", api_key=api_key, timeout_seconds=timeout_seconds) or []

    def get_network_volume(self, volume_id: str, *, api_key: str, timeout_seconds: int = 60) -> dict[str, Any]:
        return self.request("GET", f"networkvolumes/{volume_id}", api_key=api_key, timeout_seconds=timeout_seconds)

    def create_network_volume(self, *, api_key: str, name: str, size_gb: int, data_center_id: str, timeout_seconds: int = 60) -> dict[str, Any]:
        return self.request(
            "POST", "networkvolumes", api_key=api_key, timeout_seconds=timeout_seconds,
            json={"name": name, "size": size_gb, "dataCenterId": data_center_id},
        )

    def find_template_by_name(self, name: str, *, api_key: str, timeout_seconds: int = 60) -> dict[str, Any] | None:
        items = self.request(
            "GET", "templates", api_key=api_key, timeout_seconds=timeout_seconds,
            params={"includeEndpointBoundTemplates": "true"},
        ) or []
        return next((item for item in items if str(item.get("name") or "") == name), None)

    def create_template(self, *, api_key: str, name: str, image_name: str, container_disk_gb: int, registry_auth_id: str | None, env: dict[str, str], timeout_seconds: int = 60) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": name,
            "imageName": image_name,
            "category": "NVIDIA",
            "containerDiskInGb": container_disk_gb,
            "dockerEntrypoint": [],
            "dockerStartCmd": [],
            "env": env,
            "isPublic": False,
            "isServerless": True,
            "ports": [],
            "readme": "Runtime generado por AI Virtual Try-On Runtime Builder.",
            "volumeInGb": 0,
            "volumeMountPath": "/runpod-volume",
        }
        if registry_auth_id:
            payload["containerRegistryAuthId"] = registry_auth_id
        return self.request("POST", "templates", api_key=api_key, timeout_seconds=timeout_seconds, json=payload)

    def get_endpoint(self, endpoint_id: str, *, api_key: str, timeout_seconds: int = 60) -> dict[str, Any]:
        return self.request("GET", f"endpoints/{endpoint_id}", api_key=api_key, timeout_seconds=timeout_seconds)

    def create_endpoint(self, *, api_key: str, payload: dict[str, Any], timeout_seconds: int = 60) -> dict[str, Any]:
        return self.request(
            "POST", "endpoints", api_key=api_key, timeout_seconds=timeout_seconds,
            json=payload, retry_server_errors=2,
        )

    def update_endpoint(self, endpoint_id: str, *, api_key: str, payload: dict[str, Any], timeout_seconds: int = 60) -> dict[str, Any]:
        return self.request(
            "PATCH", f"endpoints/{endpoint_id}", api_key=api_key,
            timeout_seconds=timeout_seconds, json=payload, retry_server_errors=2,
        )


runpod_control_plane_service = RunPodControlPlaneService()
