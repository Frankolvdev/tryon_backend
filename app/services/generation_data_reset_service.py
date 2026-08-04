from __future__ import annotations

import json
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.common.time import utc_now
from app.models.generation_module_execution import GenerationModuleExecution
from app.models.storage_file import StorageFile
from app.models.tryon_job import TryOnJob
from app.services.storage_service import storage_service
from app.services.stripe_client_service import stripe_client_service

ACTIVE_STATUSES = {"pending", "queued", "running", "processing", "cancelling", "canceling"}
CONFIRMATION_TEXT = "BORRAR ACTIVIDAD DE PRUEBAS"


class GenerationDataResetService:
    @staticmethod
    def _table_exists(db: Session, table: str) -> bool:
        return inspect(db.get_bind()).has_table(table)

    @staticmethod
    def _count(db: Session, table: str) -> int:
        if not GenerationDataResetService._table_exists(db, table):
            return 0
        return int(db.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar() or 0)

    @staticmethod
    def _collect_file_ids(value: Any, found: set[int]) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                name = str(key).lower()
                if (name.endswith("file_id") or name.endswith("storage_file_id")) and isinstance(item, int):
                    found.add(item)
                elif (name.endswith("file_ids") or name.endswith("storage_file_ids")) and isinstance(item, list):
                    found.update(v for v in item if isinstance(v, int))
                GenerationDataResetService._collect_file_ids(item, found)
        elif isinstance(value, list):
            for item in value:
                GenerationDataResetService._collect_file_ids(item, found)

    def _file_ids(self, db: Session) -> set[int]:
        found: set[int] = set()
        if self._table_exists(db, "generation_module_executions"):
            for row in db.query(GenerationModuleExecution).all():
                try:
                    self._collect_file_ids(json.loads(row.snapshot_json or "{}"), found)
                except (TypeError, ValueError):
                    pass
        if self._table_exists(db, "tryon_jobs"):
            for row in db.query(TryOnJob).all():
                found.update(v for v in (row.person_image_file_id, row.item_image_file_id, row.result_file_id) if v)
        return found

    def preview(self, db: Session) -> dict[str, Any]:
        active_execution_ids: list[str] = []
        active_tryon_job_ids: list[int] = []
        if self._table_exists(db, "generation_module_executions"):
            active_execution_ids = [r.public_id for r in db.query(GenerationModuleExecution).all() if str(r.status).lower() in ACTIVE_STATUSES]
        if self._table_exists(db, "tryon_jobs"):
            active_tryon_job_ids = [r.id for r in db.query(TryOnJob).all() if str(r.status).lower() in ACTIVE_STATUSES]
        file_ids = self._file_ids(db)
        token_balance = int(db.execute(text("SELECT COALESCE(SUM(token_balance), 0) FROM users")).scalar() or 0)
        counts = {
            "generation_module_executions": self._count(db, "generation_module_executions"),
            "tryon_jobs": self._count(db, "tryon_jobs"),
            "generation_financial_records": self._count(db, "generation_financial_records"),
            "token_consumption_allocations": self._count(db, "token_consumption_allocations"),
            "token_transactions": self._count(db, "token_transactions"),
            "token_value_lots": self._count(db, "token_value_lots"),
            "token_purchases": self._count(db, "token_purchases"),
            "billing_payments": self._count(db, "billing_payments"),
            "billing_invoices": self._count(db, "billing_invoices"),
            "billing_events": self._count(db, "billing_events"),
            "user_subscriptions": self._count(db, "user_subscriptions"),
            "billing_customers": self._count(db, "billing_customers"),
            "external_ai_jobs": self._count(db, "external_ai_jobs"),
            "background_jobs": self._count(db, "background_jobs"),
            "storage_files": len(file_ids),
            "tokens_to_zero": token_balance,
        }
        return {
            "confirmation_text": CONFIRMATION_TEXT,
            "can_execute": not active_execution_ids and not active_tryon_job_ids,
            "active_execution_ids": active_execution_ids,
            "active_tryon_job_ids": active_tryon_job_ids,
            "counts": counts,
        }

    def execute(self, db: Session, *, confirmation: str, delete_storage_files: bool = True,
                cancel_stripe_subscriptions: bool = False) -> dict[str, Any]:
        if confirmation.strip() != CONFIRMATION_TEXT:
            raise ValueError(f"Confirmation must exactly match: {CONFIRMATION_TEXT}")
        preview = self.preview(db)
        if not preview["can_execute"]:
            raise RuntimeError("There are active generations. Cancel or finish them before resetting activity.")

        # External side effects happen first. If one fails, PostgreSQL is not cleared.
        stripe_cancelled = 0
        stripe_failures: list[str] = []
        if cancel_stripe_subscriptions and self._table_exists(db, "user_subscriptions"):
            rows = db.execute(text("SELECT provider_subscription_id FROM user_subscriptions WHERE provider_subscription_id IS NOT NULL")).all()
            for (subscription_id,) in rows:
                try:
                    stripe_client_service.cancel_subscription_immediately(db, subscription_id=subscription_id, invoice_now=False, prorate=False)
                    stripe_cancelled += 1
                except Exception as exc:  # do not silently erase a still-active remote subscription
                    stripe_failures.append(f"{subscription_id}: {exc}")
            if stripe_failures:
                raise RuntimeError("Stripe cancellation failed; no local data was deleted. " + " | ".join(stripe_failures[:5]))

        file_ids = self._file_ids(db)
        storage_rows = db.query(StorageFile).filter(StorageFile.id.in_(file_ids)).all() if file_ids else []
        deleted_storage_files = 0
        storage_failures: list[str] = []
        if delete_storage_files:
            for row in storage_rows:
                try:
                    storage_service.delete_file(db=db, storage_file=row)
                    deleted_storage_files += 1
                except Exception as exc:
                    storage_failures.append(f"{row.id}: {exc}")
            if storage_failures:
                raise RuntimeError("Storage cleanup failed; database activity was not deleted. " + " | ".join(storage_failures[:5]))

        deleted: dict[str, int] = {}
        def delete_all(table: str) -> None:
            if self._table_exists(db, table):
                result = db.execute(text(f'DELETE FROM "{table}"'))
                deleted[table] = int(result.rowcount or 0)

        try:
            # Job dependencies first.
            delete_all("background_job_attempts")
            delete_all("background_job_dependencies")
            delete_all("background_jobs")
            delete_all("external_ai_jobs")

            # Financial and token ledger dependencies.
            delete_all("token_consumption_allocations")
            delete_all("generation_financial_records")
            delete_all("token_purchases")
            delete_all("billing_invoices")
            delete_all("billing_payments")
            delete_all("user_subscriptions")
            delete_all("token_transactions")
            delete_all("token_value_lots")
            delete_all("billing_events")
            delete_all("billing_customers")

            # Generation records and optional gallery.
            delete_all("user_gallery_items")
            delete_all("generation_module_executions")
            delete_all("tryon_jobs")

            if file_ids and self._table_exists(db, "storage_files"):
                result = db.execute(text("DELETE FROM storage_files WHERE id = ANY(:ids)"), {"ids": list(file_ids)})
                deleted["storage_files"] = int(result.rowcount or 0)

            # Keep users, but reset all token balances exactly to zero.
            result = db.execute(text("UPDATE users SET token_balance = 0 WHERE token_balance <> 0"))
            zeroed_users = int(result.rowcount or 0)
            db.commit()
        except Exception:
            db.rollback()
            raise

        return {
            "success": True,
            "deleted": deleted,
            "deleted_storage_files": deleted_storage_files,
            "zeroed_users": zeroed_users,
            "stripe_subscriptions_cancelled": stripe_cancelled,
            "completed_at": utc_now().isoformat(),
        }


generation_data_reset_service = GenerationDataResetService()
