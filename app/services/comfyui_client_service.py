import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from sqlalchemy.orm import Session

from app.common.enums import IntegrationProvider
from app.common.exceptions import ConflictException
from app.services.integration_service import integration_service


class ComfyUIClientService:
    def _get_config(self, db: Session):
        config = integration_service.get_config(db, IntegrationProvider.COMFYUI)

        if not config.is_enabled:
            raise ConflictException("ComfyUI integration is disabled.")

        if not config.base_url:
            raise ConflictException("ComfyUI base URL is not configured.")

        return config

    def _base_url(self, db: Session) -> str:
        config = self._get_config(db)
        return config.base_url.rstrip("/")

    def health_check(self, db: Session) -> dict[str, Any]:
        base_url = self._base_url(db)

        with httpx.Client(timeout=10.0) as client:
            response = client.get(f"{base_url}/system_stats")

        response.raise_for_status()

        return {
            "healthy": True,
            "base_url": base_url,
            "status_code": response.status_code,
            "response": response.json(),
        }

    def queue_prompt(
        self,
        db: Session,
        *,
        workflow: dict[str, Any],
        client_id: str | None = None,
    ) -> dict[str, Any]:
        base_url = self._base_url(db)
        client_id = client_id or str(uuid4())

        payload = {
            "prompt": workflow,
            "client_id": client_id,
        }

        with httpx.Client(timeout=60.0) as client:
            response = client.post(
                f"{base_url}/prompt",
                json=payload,
            )

        response.raise_for_status()
        return response.json()

    def get_history(
        self,
        db: Session,
        *,
        prompt_id: str,
    ) -> dict[str, Any]:
        base_url = self._base_url(db)

        with httpx.Client(timeout=30.0) as client:
            response = client.get(f"{base_url}/history/{prompt_id}")

        response.raise_for_status()
        return response.json()

    def upload_image(
        self,
        db: Session,
        *,
        file_path: str,
        filename: str | None = None,
        subfolder: str = "",
        image_type: str = "input",
        overwrite: bool = True,
    ) -> dict[str, Any]:
        base_url = self._base_url(db)

        path = Path(file_path)

        if not path.exists():
            raise ConflictException("Upload file does not exist.")

        upload_filename = filename or path.name

        data = {
            "type": image_type,
            "subfolder": subfolder,
            "overwrite": str(overwrite).lower(),
        }

        with path.open("rb") as file:
            files = {
                "image": (
                    upload_filename,
                    file,
                    "application/octet-stream",
                )
            }

            with httpx.Client(timeout=120.0) as client:
                response = client.post(
                    f"{base_url}/upload/image",
                    data=data,
                    files=files,
                )

        response.raise_for_status()
        return response.json()

    def get_view_url(
        self,
        db: Session,
        *,
        filename: str,
        subfolder: str = "",
        image_type: str = "output",
    ) -> str:
        base_url = self._base_url(db)

        return (
            f"{base_url}/view"
            f"?filename={filename}"
            f"&subfolder={subfolder}"
            f"&type={image_type}"
        )

    def extract_output_images_from_history(
        self,
        history: dict[str, Any],
        *,
        prompt_id: str,
    ) -> list[dict[str, Any]]:
        prompt_history = history.get(prompt_id) or {}

        outputs = prompt_history.get("outputs") or {}
        images: list[dict[str, Any]] = []

        for node_id, node_output in outputs.items():
            for image in node_output.get("images", []) or []:
                images.append(
                    {
                        "node_id": node_id,
                        "filename": image.get("filename"),
                        "subfolder": image.get("subfolder") or "",
                        "type": image.get("type") or "output",
                    }
                )

        return images

    def load_workflow_file(self, workflow_path: str) -> dict[str, Any]:
        path = Path(workflow_path)

        if not path.exists():
            raise ConflictException("Workflow file does not exist.")

        return json.loads(path.read_text(encoding="utf-8"))


comfyui_client_service = ComfyUIClientService()