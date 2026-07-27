from __future__ import annotations

from typing import Any

import httpx


class RunPodControlPlaneService:
    """Cliente del REST API de RunPod para recursos de infraestructura.

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

    def request(
        self,
        method: str,
        path: str,
        *,
        api_key: str,
        timeout_seconds: int = 60,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        with httpx.Client(timeout=float(timeout_seconds)) as client:
            response = client.request(
                method,
                f"{self.BASE_URL}/{path.lstrip('/')}",
                headers=self._headers(api_key),
                json=json,
                params=params,
            )
            response.raise_for_status()
            if response.status_code == 204 or not response.content:
                return None
            return response.json()

    def account_probe(self, *, api_key: str, timeout_seconds: int = 30) -> dict[str, Any]:
        endpoints = self.request(
            "GET", "endpoints", api_key=api_key, timeout_seconds=timeout_seconds
        )
        return {"endpoint_count": len(endpoints or [])}

    def list_network_volumes(self, *, api_key: str, timeout_seconds: int = 60) -> list[dict[str, Any]]:
        return self.request(
            "GET", "networkvolumes", api_key=api_key, timeout_seconds=timeout_seconds
        ) or []

    def get_network_volume(self, volume_id: str, *, api_key: str, timeout_seconds: int = 60) -> dict[str, Any]:
        return self.request(
            "GET", f"networkvolumes/{volume_id}", api_key=api_key, timeout_seconds=timeout_seconds
        )

    def create_network_volume(
        self,
        *,
        api_key: str,
        name: str,
        size_gb: int,
        data_center_id: str,
        timeout_seconds: int = 60,
    ) -> dict[str, Any]:
        return self.request(
            "POST",
            "networkvolumes",
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            json={"name": name, "size": size_gb, "dataCenterId": data_center_id},
        )

    def find_template_by_name(self, name: str, *, api_key: str, timeout_seconds: int = 60) -> dict[str, Any] | None:
        items = self.request(
            "GET",
            "templates",
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            params={"includeEndpointBoundTemplates": "true"},
        ) or []
        return next((item for item in items if str(item.get("name") or "") == name), None)

    def create_template(
        self,
        *,
        api_key: str,
        name: str,
        image_name: str,
        container_disk_gb: int,
        registry_auth_id: str | None,
        env: dict[str, str],
        timeout_seconds: int = 60,
    ) -> dict[str, Any]:
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
        return self.request(
            "POST", "templates", api_key=api_key, timeout_seconds=timeout_seconds, json=payload
        )

    def get_endpoint(self, endpoint_id: str, *, api_key: str, timeout_seconds: int = 60) -> dict[str, Any]:
        return self.request(
            "GET", f"endpoints/{endpoint_id}", api_key=api_key, timeout_seconds=timeout_seconds
        )

    def create_endpoint(self, *, api_key: str, payload: dict[str, Any], timeout_seconds: int = 60) -> dict[str, Any]:
        return self.request(
            "POST", "endpoints", api_key=api_key, timeout_seconds=timeout_seconds, json=payload
        )

    def update_endpoint(self, endpoint_id: str, *, api_key: str, payload: dict[str, Any], timeout_seconds: int = 60) -> dict[str, Any]:
        return self.request(
            "PATCH", f"endpoints/{endpoint_id}", api_key=api_key, timeout_seconds=timeout_seconds, json=payload
        )


runpod_control_plane_service = RunPodControlPlaneService()
