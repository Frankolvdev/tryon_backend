from pathlib import Path
from sqlalchemy.orm import Session

from app.common.enums import IntegrationProvider
from app.common.exceptions import ConflictException
from app.models.tryon_job import TryOnJob
from app.repositories.storage_file_repository import storage_file_repository
from app.services.comfyui_client_service import comfyui_client_service
from app.services.comfyui_workflow_service import comfyui_workflow_service
from app.services.integration_service import integration_service
from app.services.storage_service import storage_service


class ComfyUITryOnService:
    def _local_file_path(self, object_key: str) -> str:
        return str(Path("storage") / object_key)

    def _get_comfyui_config(self, db: Session) -> dict:
        config = integration_service.get_config(db, IntegrationProvider.COMFYUI)
        return integration_service._parse_json(config.config_json)

    def _build_patches(
        self,
        db: Session,
        *,
        job: TryOnJob,
        uploaded_person: dict,
        uploaded_item: dict,
    ) -> list[dict]:
        config = self._get_comfyui_config(db)

        person_node_id = config.get("person_image_node_id", "person_image")
        item_node_id = config.get("item_image_node_id", "item_image")
        prompt_node_id = config.get("prompt_node_id")

        person_image_path = config.get("person_image_path", ["inputs", "image"])
        item_image_path = config.get("item_image_path", ["inputs", "image"])
        prompt_path = config.get("prompt_path", ["inputs", "text"])

        patches = [
            {
                "node_id": person_node_id,
                "path": person_image_path,
                "value": uploaded_person.get("name") or uploaded_person.get("filename"),
            },
            {
                "node_id": item_node_id,
                "path": item_image_path,
                "value": uploaded_item.get("name") or uploaded_item.get("filename"),
            },
        ]

        if prompt_node_id and job.prompt:
            patches.append(
                {
                    "node_id": prompt_node_id,
                    "path": prompt_path,
                    "value": job.prompt,
                }
            )

        return patches

    def execute_tryon_job(
        self,
        db: Session,
        *,
        job: TryOnJob,
    ):
        person_file = storage_file_repository.get_by_id(db, job.person_image_file_id)
        item_file = storage_file_repository.get_by_id(db, job.item_image_file_id)

        if not person_file or not item_file:
            raise ConflictException("Try-on source files are missing.")

        person_path = self._local_file_path(person_file.object_key)
        item_path = self._local_file_path(item_file.object_key)

        uploaded_person = comfyui_client_service.upload_image(
            db=db,
            file_path=person_path,
            filename=f"person_{job.id}.jpg",
            overwrite=True,
        )

        uploaded_item = comfyui_client_service.upload_image(
            db=db,
            file_path=item_path,
            filename=f"item_{job.id}.jpg",
            overwrite=True,
        )

        workflow_name = job.comfy_workflow_name or "tryon_workflow.json"

        result = comfyui_workflow_service.run_workflow(
            db=db,
            workflow_name=workflow_name,
            patches=self._build_patches(
                db=db,
                job=job,
                uploaded_person=uploaded_person,
                uploaded_item=uploaded_item,
            ),
            client_id=None,
            wait_for_result=True,
        )

        images = result.get("images") or []

        if not images:
            raise ConflictException("ComfyUI workflow completed without output images.")

        first_image = images[0]

        result_url = comfyui_client_service.get_view_url(
            db=db,
            filename=first_image["filename"],
            subfolder=first_image.get("subfolder") or "",
            image_type=first_image.get("type") or "output",
        )

        return storage_service.create_remote_result_record(
            db=db,
            user_id=job.user_id,
            public_url=result_url,
            folder="tryon-results",
            original_filename=f"tryon-result-{job.id}.jpg",
            content_type="image/jpeg",
        )


comfyui_tryon_service = ComfyUITryOnService()