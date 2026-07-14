from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.common.enums import IntegrationProvider, QualityMode, TryOnItemType, TryOnJobStatus
from app.common.exceptions import ConflictException, ForbiddenException, NotFoundException
from app.common.time import utc_now
from app.models.tryon_job import TryOnJob
from app.models.user import User
from app.repositories.storage_file_repository import storage_file_repository
from app.repositories.tryon_job_repository import tryon_job_repository
from app.schemas.runpod_external import RunPodSubmitRequest
from app.schemas.tryon import TryOnJobAdminUpdate
from app.services.external_ai_job_service import external_ai_job_service
from app.services.integration_service import integration_service
from app.services.pricing_service import pricing_service
from app.services.runpod_config_service import runpod_config_service
from app.services.runtime_settings_service import runtime_settings_service
from app.services.storage_service import storage_service
from app.services.token_service import token_service


class TryOnService:
    def create_tryon_job(
        self,
        db: Session,
        *,
        user: User,
        person_image: UploadFile,
        item_image: UploadFile,
        item_type: TryOnItemType,
        quality_mode: QualityMode,
        prompt: str | None = None,
    ) -> TryOnJob:
        if not runtime_settings_service.tryon_enabled(db):
            raise ForbiddenException("Try-on generation is currently disabled.")

        if item_type == TryOnItemType.FOOTWEAR and not runtime_settings_service.footwear_tryon_enabled(db):
            raise ForbiddenException("Footwear try-on is currently disabled.")

        if quality_mode == QualityMode.HIGH and not runtime_settings_service.high_quality_enabled(db):
            raise ForbiddenException("High quality mode is currently disabled.")

        pricing_rule = pricing_service.get_tryon_price(
            db,
            item_type=item_type,
            quality_mode=quality_mode,
        )

        runpod_config = runpod_config_service.get_active_config(db)

        token_service.debit_tokens(
            db=db,
            user_id=user.id,
            amount=pricing_rule.tokens_cost,
            source="tryon",
            reference_id=None,
            description="Try-on job token consumption",
        )

        person_file = storage_service.save_upload_file(
            db=db,
            user_id=user.id,
            file=person_image,
            folder="person-images",
        )

        item_file = storage_service.save_upload_file(
            db=db,
            user_id=user.id,
            file=item_image,
            folder="item-images",
        )

        job = TryOnJob(
            user_id=user.id,
            person_image_file_id=person_file.id,
            item_image_file_id=item_file.id,
            pricing_rule_id=pricing_rule.id,
            runpod_config_id=runpod_config.id if runpod_config else None,
            item_type=item_type.value,
            quality_mode=quality_mode.value,
            status=TryOnJobStatus.QUEUED.value,
            tokens_cost=pricing_rule.tokens_cost,
            estimated_gpu_seconds=pricing_rule.estimated_gpu_seconds,
            estimated_gpu_cost_cents=pricing_rule.estimated_gpu_cost_cents,
            prompt=prompt,
            comfy_workflow_name=(
                runpod_config.comfy_workflow_name
                if runpod_config and runpod_config.comfy_workflow_name
                else "tryon_workflow.json"
            ),
        )

        db.add(job)
        db.commit()
        db.refresh(job)

        if runtime_settings_service.runpod_enabled(db):
            self.submit_runpod_tryon_job(db=db, job_id=job.id)
            return tryon_job_repository.get_by_id(db, job.id)

        if self._comfyui_enabled(db):
            self.process_comfyui_tryon_job(db=db, job_id=job.id)
            return tryon_job_repository.get_by_id(db, job.id)

        self.process_local_mock_job(db, job.id)
        return tryon_job_repository.get_by_id(db, job.id)

    def _comfyui_enabled(self, db: Session) -> bool:
        try:
            config = integration_service.get_config(db, IntegrationProvider.COMFYUI)
            return bool(config.is_enabled)
        except Exception:
            return False

    def process_comfyui_tryon_job(
        self,
        db: Session,
        *,
        job_id: int,
    ) -> TryOnJob:
        job = tryon_job_repository.get_by_id(db, job_id)

        if not job:
            raise NotFoundException("Try-on job not found.")

        job.status = TryOnJobStatus.PROCESSING.value
        db.add(job)
        db.commit()
        db.refresh(job)

        try:
            from app.services.comfyui_tryon_service import comfyui_tryon_service

            result_file = comfyui_tryon_service.execute_tryon_job(
                db=db,
                job=job,
            )

            job.result_file_id = result_file.id
            job.status = TryOnJobStatus.COMPLETED.value
            job.completed_at = utc_now()
            job.actual_gpu_seconds = job.estimated_gpu_seconds
            job.actual_gpu_cost_cents = job.estimated_gpu_cost_cents

        except Exception as error:
            job.status = TryOnJobStatus.FAILED.value
            job.error_message = str(error)

        db.add(job)
        db.commit()
        db.refresh(job)

        return job

    def submit_runpod_tryon_job(
        self,
        db: Session,
        *,
        job_id: int,
    ) -> TryOnJob:
        job = tryon_job_repository.get_by_id(db, job_id)

        if not job:
            raise NotFoundException("Try-on job not found.")

        runpod_config = runpod_config_service.get_active_config(db)

        if not runpod_config:
            raise ConflictException("No active RunPod configuration found.")

        if not runpod_config.endpoint_id:
            raise ConflictException("Active RunPod configuration does not have endpoint_id.")

        person_file = storage_file_repository.get_by_id(db, job.person_image_file_id)
        item_file = storage_file_repository.get_by_id(db, job.item_image_file_id)

        if not person_file or not item_file:
            raise ConflictException("Try-on job files are missing.")

        payload = {
            "job_id": job.id,
            "user_id": job.user_id,
            "item_type": job.item_type,
            "quality_mode": job.quality_mode,
            "prompt": job.prompt,
            "workflow_name": job.comfy_workflow_name,
            "person_image_url": person_file.public_url,
            "item_image_url": item_file.public_url,
            "person_image_file_id": person_file.id,
            "item_image_file_id": item_file.id,
        }

        external_job = external_ai_job_service.submit_runpod_job(
            db=db,
            data=RunPodSubmitRequest(
                endpoint_id=runpod_config.endpoint_id,
                input=payload,
                internal_job_type="tryon",
                internal_job_id=job.id,
            ),
        )

        job.status = TryOnJobStatus.PENDING.value
        job.runpod_job_id = external_job.provider_job_id

        db.add(job)
        db.commit()
        db.refresh(job)

        return job

    def process_local_mock_job(
        self,
        db: Session,
        job_id: int,
    ) -> TryOnJob:
        job = tryon_job_repository.get_by_id(db, job_id)

        if not job:
            raise NotFoundException("Try-on job not found.")

        job.status = TryOnJobStatus.PROCESSING.value
        db.add(job)
        db.commit()
        db.refresh(job)

        person_file = storage_file_repository.get_by_id(
            db,
            job.person_image_file_id,
        )

        if not person_file:
            job.status = TryOnJobStatus.FAILED.value
            job.error_message = "Person image file not found."
            db.add(job)
            db.commit()
            db.refresh(job)
            return job

        result_file = storage_service.create_local_copy_result(
            db=db,
            user_id=job.user_id,
            source_file=person_file,
            folder="tryon-results",
        )

        job.result_file_id = result_file.id
        job.status = TryOnJobStatus.COMPLETED.value
        job.completed_at = utc_now()
        job.actual_gpu_seconds = job.estimated_gpu_seconds
        job.actual_gpu_cost_cents = job.estimated_gpu_cost_cents

        db.add(job)
        db.commit()
        db.refresh(job)

        return job

    def list_my_jobs(
        self,
        db: Session,
        *,
        user: User,
        skip: int = 0,
        limit: int = 50,
    ) -> list[TryOnJob]:
        return tryon_job_repository.list_by_user_id(
            db,
            user.id,
            skip=skip,
            limit=limit,
        )

    def get_my_job(
        self,
        db: Session,
        *,
        user: User,
        job_id: int,
    ) -> TryOnJob:
        job = tryon_job_repository.get_by_id(db, job_id)

        if not job:
            raise NotFoundException("Try-on job not found.")

        if job.user_id != user.id:
            raise ForbiddenException("You do not have access to this job.")

        return job

    def admin_list_jobs(
        self,
        db: Session,
        *,
        skip: int = 0,
        limit: int = 50,
    ) -> list[TryOnJob]:
        return tryon_job_repository.list_all(
            db,
            skip=skip,
            limit=limit,
        )

    def admin_get_job(
        self,
        db: Session,
        job_id: int,
    ) -> TryOnJob:
        job = tryon_job_repository.get_by_id(db, job_id)

        if not job:
            raise NotFoundException("Try-on job not found.")

        return job

    def admin_update_job(
        self,
        db: Session,
        *,
        job_id: int,
        data: TryOnJobAdminUpdate,
    ) -> TryOnJob:
        job = self.admin_get_job(db, job_id)

        update_data = data.model_dump(exclude_unset=True)

        return tryon_job_repository.update(
            db,
            db_obj=job,
            data=update_data,
        )


tryon_service = TryOnService()