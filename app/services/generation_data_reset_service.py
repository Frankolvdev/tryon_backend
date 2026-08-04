from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from sqlalchemy import inspect, or_
from sqlalchemy.orm import Session

from app.common.time import utc_now
from app.models.background_job import BackgroundJob
from app.models.external_ai_job import ExternalAiJob
from app.models.generation_financial_record import GenerationFinancialRecord
from app.models.generation_module_execution import GenerationModuleExecution
from app.models.storage_file import StorageFile
from app.models.token_consumption_allocation import TokenConsumptionAllocation
from app.models.token_transaction import TokenTransaction
from app.models.token_value_lot import TokenValueLot
from app.models.tryon_job import TryOnJob
from app.models.user import User
from app.models.user_gallery_item import UserGalleryItem
from app.services.storage_service import storage_service


ACTIVE_STATUSES = {"pending", "queued", "running", "processing", "cancelling", "canceling"}
GENERATION_TOKEN_SOURCES = {
    "generation_module", "generation_module_adjustment", "generation_module_refund",
    "generation_module_price_refund", "tryon", "tryon_refund",
}
CONFIRMATION_TEXT = "BORRAR GENERACIONES"


class GenerationDataResetService:
    @staticmethod
    def _collect_file_ids(value: Any, found: set[int]) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                normalized = str(key).lower()
                if (normalized.endswith("file_id") or normalized.endswith("storage_file_id")) and isinstance(item, int):
                    found.add(item)
                elif (normalized.endswith("file_ids") or normalized.endswith("storage_file_ids")) and isinstance(item, list):
                    found.update(v for v in item if isinstance(v, int))
                GenerationDataResetService._collect_file_ids(item, found)
        elif isinstance(value, list):
            for item in value:
                GenerationDataResetService._collect_file_ids(item, found)

    def _context(self, db: Session) -> dict[str, Any]:
        executions = db.query(GenerationModuleExecution).all()
        tryon_jobs = db.query(TryOnJob).all()
        execution_ids = [row.public_id for row in executions]
        tryon_ids = [row.id for row in tryon_jobs]
        file_ids: set[int] = set()
        for row in executions:
            try:
                self._collect_file_ids(json.loads(row.snapshot_json or "{}"), file_ids)
            except (TypeError, ValueError):
                continue
        for row in tryon_jobs:
            file_ids.update(v for v in (row.person_image_file_id, row.item_image_file_id, row.result_file_id) if v)
        # The gallery module is optional in older or partially migrated installations.
        # Never make the maintenance preview fail just because its table is absent.
        gallery_table_available = inspect(db.get_bind()).has_table(UserGalleryItem.__tablename__)
        gallery_rows = []
        if gallery_table_available and (tryon_ids or file_ids):
            gallery_rows = db.query(UserGalleryItem).filter(
                or_(
                    UserGalleryItem.tryon_job_id.in_(tryon_ids) if tryon_ids else False,
                    UserGalleryItem.source_file_id.in_(file_ids) if file_ids else False,
                    UserGalleryItem.result_file_id.in_(file_ids) if file_ids else False,
                )
            ).all()
        for row in gallery_rows:
            file_ids.update(v for v in (row.source_file_id, row.result_file_id) if v)
        active_exec = [row.public_id for row in executions if row.status.lower() in ACTIVE_STATUSES]
        active_tryon = [row.id for row in tryon_jobs if row.status.lower() in ACTIVE_STATUSES]
        allocations = db.query(TokenConsumptionAllocation).filter(
            TokenConsumptionAllocation.execution_id.in_(execution_ids)
        ).all() if execution_ids else []
        financial_count = db.query(GenerationFinancialRecord).filter(
            GenerationFinancialRecord.execution_id.in_(execution_ids)
        ).count() if execution_ids else 0
        token_tx_count = db.query(TokenTransaction).filter(
            TokenTransaction.source.in_(GENERATION_TOKEN_SOURCES)
        ).count()
        external_count = db.query(ExternalAiJob).filter(ExternalAiJob.internal_job_type == "tryon").count()
        background_count = db.query(BackgroundJob).filter(
            or_(BackgroundJob.tryon_job_id.in_(tryon_ids) if tryon_ids else False,
                BackgroundJob.external_ai_job_id.isnot(None))
        ).count() if tryon_ids else 0
        return {
            "executions": executions, "tryon_jobs": tryon_jobs, "execution_ids": execution_ids,
            "tryon_ids": tryon_ids, "file_ids": file_ids, "gallery_rows": gallery_rows,
            "allocations": allocations, "gallery_table_available": gallery_table_available,
            "active_execution_ids": active_exec,
            "active_tryon_job_ids": active_tryon, "financial_count": financial_count,
            "token_transaction_count": token_tx_count, "external_job_count": external_count,
            "background_job_count": background_count,
        }

    def preview(self, db: Session) -> dict[str, Any]:
        ctx = self._context(db)
        restored = sum(max(a.tokens_allocated - a.tokens_reversed, 0) for a in ctx["allocations"])
        return {
            "confirmation_text": CONFIRMATION_TEXT,
            "can_execute": not ctx["active_execution_ids"] and not ctx["active_tryon_job_ids"],
            "active_execution_ids": ctx["active_execution_ids"],
            "active_tryon_job_ids": ctx["active_tryon_job_ids"],
            "counts": {
                "generation_module_executions": len(ctx["executions"]),
                "tryon_jobs": len(ctx["tryon_jobs"]),
                "generation_financial_records": ctx["financial_count"],
                "token_consumption_allocations": len(ctx["allocations"]),
                "generation_token_transactions": ctx["token_transaction_count"],
                "external_ai_jobs": ctx["external_job_count"],
                "background_jobs": ctx["background_job_count"],
                "gallery_items": len(ctx["gallery_rows"]),
                "gallery_table_available": ctx["gallery_table_available"],
                "storage_files": len(ctx["file_ids"]),
                "tokens_to_restore": restored,
            },
        }

    def execute(self, db: Session, *, confirmation: str, delete_storage_files: bool = True) -> dict[str, Any]:
        if confirmation.strip() != CONFIRMATION_TEXT:
            raise ValueError(f"Confirmation must exactly match: {CONFIRMATION_TEXT}")
        ctx = self._context(db)
        if ctx["active_execution_ids"] or ctx["active_tryon_job_ids"]:
            raise RuntimeError("There are active generations. Cancel or finish them before resetting data.")

        storage_rows = db.query(StorageFile).filter(StorageFile.id.in_(ctx["file_ids"])).all() if ctx["file_ids"] else []
        deleted_storage = 0
        if delete_storage_files:
            for storage_file in storage_rows:
                storage_service.delete_file(db=db, storage_file=storage_file)
                deleted_storage += 1

        restored_by_user: dict[int, int] = defaultdict(int)
        for allocation in ctx["allocations"]:
            amount = max(allocation.tokens_allocated - allocation.tokens_reversed, 0)
            if amount:
                lot = db.query(TokenValueLot).filter(TokenValueLot.id == allocation.lot_id).with_for_update().first()
                if lot:
                    lot.remaining_tokens = min(lot.original_tokens, lot.remaining_tokens + amount)
                restored_by_user[allocation.user_id] += amount

        for user_id, amount in restored_by_user.items():
            user = db.query(User).filter(User.id == user_id).with_for_update().first()
            if user:
                user.token_balance += amount
                db.add(TokenTransaction(
                    user_id=user.id, transaction_type="credit", amount=amount,
                    balance_after=user.token_balance, source="admin_generation_reset",
                    reference_id=None, description="Tokens restored by generation test-data reset.",
                ))

        # Break nullable references before deleting job rows.
        if ctx["tryon_ids"]:
            db.query(BackgroundJob).filter(BackgroundJob.tryon_job_id.in_(ctx["tryon_ids"])).update(
                {BackgroundJob.tryon_job_id: None}, synchronize_session=False
            )
        external_ids = [r.id for r in db.query(ExternalAiJob.id).filter(ExternalAiJob.internal_job_type == "tryon").all()]
        if external_ids:
            db.query(BackgroundJob).filter(BackgroundJob.external_ai_job_id.in_(external_ids)).update(
                {BackgroundJob.external_ai_job_id: None}, synchronize_session=False
            )

        for row in ctx["gallery_rows"]:
            db.delete(row)
        if ctx["execution_ids"]:
            db.query(TokenConsumptionAllocation).filter(TokenConsumptionAllocation.execution_id.in_(ctx["execution_ids"])).delete(synchronize_session=False)
            db.query(GenerationFinancialRecord).filter(GenerationFinancialRecord.execution_id.in_(ctx["execution_ids"])).delete(synchronize_session=False)
            db.query(TokenTransaction).filter(
                TokenTransaction.reference_id.in_(ctx["execution_ids"]),
                TokenTransaction.source.in_(GENERATION_TOKEN_SOURCES),
            ).delete(synchronize_session=False)
        if ctx["tryon_ids"]:
            tryon_refs = [str(v) for v in ctx["tryon_ids"]]
            db.query(TokenTransaction).filter(
                TokenTransaction.reference_id.in_(tryon_refs), TokenTransaction.source.in_(GENERATION_TOKEN_SOURCES)
            ).delete(synchronize_session=False)
        db.query(ExternalAiJob).filter(ExternalAiJob.internal_job_type == "tryon").delete(synchronize_session=False)
        db.query(GenerationModuleExecution).delete(synchronize_session=False)
        db.query(TryOnJob).delete(synchronize_session=False)

        if storage_rows:
            db.query(StorageFile).filter(StorageFile.id.in_([r.id for r in storage_rows])).delete(synchronize_session=False)
        db.commit()
        return {
            "success": True,
            "deleted_storage_files": deleted_storage,
            "restored_tokens": sum(restored_by_user.values()),
            "restored_users": len(restored_by_user),
            "completed_at": utc_now().isoformat(),
        }


generation_data_reset_service = GenerationDataResetService()
