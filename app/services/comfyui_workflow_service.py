import time
from copy import deepcopy
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.common.enums import IntegrationProvider
from app.common.exceptions import ConflictException
from app.services.comfyui_client_service import comfyui_client_service
from app.services.integration_service import integration_service


class ComfyUIWorkflowService:
    def _get_config_dict(self, db: Session) -> dict[str, Any]:
        config = integration_service.get_config(db, IntegrationProvider.COMFYUI)
        return integration_service._parse_json(config.config_json)

    def _workflows_dir(self, db: Session) -> Path:
        config = self._get_config_dict(db)
        workflows_dir = config.get("workflows_dir") or "workflows"
        path = Path(workflows_dir)

        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)

        return path

    def list_workflows(self, db: Session) -> list[str]:
        workflows_dir = self._workflows_dir(db)

        return sorted(
            [
                item.name
                for item in workflows_dir.glob("*.json")
                if item.is_file()
            ]
        )

    def load_workflow(
        self,
        db: Session,
        *,
        workflow_name: str,
    ) -> dict[str, Any]:
        workflows_dir = self._workflows_dir(db)
        workflow_path = workflows_dir / workflow_name

        if not workflow_path.exists():
            raise ConflictException(f"Workflow {workflow_name} does not exist.")

        return comfyui_client_service.load_workflow_file(str(workflow_path))

    def _normalize_patch(self, patch):
        if isinstance(patch, dict):
            return patch["node_id"], patch["path"], patch["value"]

        return patch.node_id, patch.path, patch.value

    def apply_patch(
        self,
        workflow: dict[str, Any],
        *,
        node_id: str,
        path: list[str | int],
        value: Any,
    ) -> dict[str, Any]:
        patched = workflow

        if node_id not in patched:
            raise ConflictException(f"Node {node_id} does not exist in workflow.")

        current: Any = patched[node_id]

        for key in path[:-1]:
            if isinstance(current, list):
                current = current[int(key)]
            else:
                current = current[str(key)]

        last_key = path[-1]

        if isinstance(current, list):
            current[int(last_key)] = value
        else:
            current[str(last_key)] = value

        return patched

    def apply_patches(
        self,
        workflow: dict[str, Any],
        patches: list,
    ) -> dict[str, Any]:
        patched = deepcopy(workflow)

        for patch in patches:
            node_id, path, value = self._normalize_patch(patch)

            patched = self.apply_patch(
                patched,
                node_id=node_id,
                path=path,
                value=value,
            )

        return patched

    def run_workflow(
        self,
        db: Session,
        *,
        workflow_name: str,
        patches: list,
        client_id: str | None = None,
        wait_for_result: bool = True,
    ) -> dict[str, Any]:
        workflow = self.load_workflow(db, workflow_name=workflow_name)
        patched_workflow = self.apply_patches(workflow, patches)

        queue_response = comfyui_client_service.queue_prompt(
            db,
            workflow=patched_workflow,
            client_id=client_id,
        )

        prompt_id = queue_response.get("prompt_id")

        if not wait_for_result or not prompt_id:
            return {
                "prompt_id": prompt_id,
                "status": "queued",
                "images": [],
                "raw_queue_response": queue_response,
                "raw_history": None,
            }

        config = self._get_config_dict(db)
        timeout_seconds = int(config.get("poll_timeout_seconds", 300))
        interval_seconds = float(config.get("poll_interval_seconds", 2))

        started = time.time()
        history = None
        images: list[dict[str, Any]] = []

        while time.time() - started < timeout_seconds:
            history = comfyui_client_service.get_history(
                db,
                prompt_id=prompt_id,
            )

            if prompt_id in history:
                images = comfyui_client_service.extract_output_images_from_history(
                    history,
                    prompt_id=prompt_id,
                )

                if images:
                    break

            time.sleep(interval_seconds)

        return {
            "prompt_id": prompt_id,
            "status": "completed" if images else "timeout",
            "images": images,
            "raw_queue_response": queue_response,
            "raw_history": history,
        }


comfyui_workflow_service = ComfyUIWorkflowService()