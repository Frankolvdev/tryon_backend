from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.common.exceptions import ConflictException, NotFoundException
from app.models.generation_module_execution import GenerationModuleExecution
from app.models.storage_file import StorageFile
from app.models.user_gallery_item import UserGalleryItem
from app.services.storage_service import storage_service


class AdminUserStorageService:
    """Safe admin-only cleanup of a user's generation media.

    Financial records are deliberately NOT deleted. Removing a generation from
    the user's storage/history must never erase the accounting trail.
    """

    TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


    def list_files(
        self,
        db: Session,
        *,
        user_id: int,
        asset_kind: str | None = None,
        search: str | None = None,
        skip: int = 0,
        limit: int = 500,
    ) -> dict:
        conditions = [StorageFile.user_id == user_id]
        normalized_kind = str(asset_kind or "").strip().lower()
        if normalized_kind == "inputs":
            conditions.append(StorageFile.object_key.like("generation-inputs/%"))
        elif normalized_kind == "results":
            conditions.append(StorageFile.object_key.like("generation-results/%"))
        elif normalized_kind == "library":
            conditions.append(StorageFile.object_key.like("user-library/%"))
        elif normalized_kind == "other":
            conditions.extend((
                ~StorageFile.object_key.like("generation-inputs/%"),
                ~StorageFile.object_key.like("generation-results/%"),
                ~StorageFile.object_key.like("user-library/%"),
            ))
        if search:
            pattern = f"%{search.strip().lower()}%"
            conditions.append(or_(
                func.lower(func.coalesce(StorageFile.original_filename, "")).like(pattern),
                func.lower(StorageFile.object_key).like(pattern),
                func.lower(func.coalesce(StorageFile.content_type, "")).like(pattern),
                func.lower(StorageFile.provider).like(pattern),
            ))
        total = int(db.scalar(select(func.count(StorageFile.id)).where(*conditions)) or 0)
        total_bytes = int(db.scalar(select(func.coalesce(func.sum(StorageFile.size_bytes), 0)).where(*conditions)) or 0)
        items = list(db.scalars(
            select(StorageFile).where(*conditions).order_by(StorageFile.created_at.desc()).offset(skip).limit(limit)
        ).all())
        return {"items": items, "total": total, "total_size_bytes": total_bytes, "skip": skip, "limit": limit}

    def delete_generation(
        self,
        db: Session,
        *,
        user_id: int,
        execution_id: UUID,
    ) -> dict:
        row = db.scalar(
            select(GenerationModuleExecution).where(
                GenerationModuleExecution.public_id == str(execution_id),
                GenerationModuleExecution.user_id == user_id,
            )
        )
        if row is None:
            raise NotFoundException("Generation not found for this user.")
        if row.status not in self.TERMINAL_STATUSES:
            raise ConflictException(
                "A generation that is still queued or running cannot be deleted."
            )

        # Result files are stored below a generation-specific directory. Inputs
        # intentionally live elsewhere and are not deleted here because they can
        # be useful/reused independently and are managed from the Files filter.
        prefix = f"generation-results/{execution_id}/%"
        result_files = list(
            db.scalars(
                select(StorageFile).where(
                    StorageFile.user_id == user_id,
                    StorageFile.object_key.like(prefix),
                )
            ).all()
        )
        result_ids = [item.id for item in result_files]

        # Gallery rows can RESTRICT deletion of a result file. Deleting a
        # generation from storage also removes its gallery references, but not
        # unrelated user-library/input files.
        gallery_rows_deleted = 0
        if result_ids:
            gallery_result = db.execute(
                delete(UserGalleryItem).where(
                    UserGalleryItem.user_id == user_id,
                    UserGalleryItem.result_file_id.in_(result_ids),
                )
            )
            gallery_rows_deleted = int(gallery_result.rowcount or 0)
            db.flush()

        deleted_files = 0
        for item in result_files:
            storage_service.delete_file(db, storage_file=item)
            db.delete(item)
            deleted_files += 1

        # Keep GenerationFinancialRecord / TokenConsumptionAllocation untouched:
        # they are accounting evidence and must survive a media cleanup.
        db.delete(row)
        db.commit()

        return {
            "execution_id": str(execution_id),
            "deleted_result_files": deleted_files,
            "deleted_gallery_items": gallery_rows_deleted,
            "financial_history_preserved": True,
        }


admin_user_storage_service = AdminUserStorageService()
