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

    def _preserved_account_file_ids(self, db: Session) -> set[int]:
        """Files that belong to a surviving account rather than test activity."""
        if not self._table_exists(db, "users"):
            return set()
        return {
            int(value)
            for value in db.execute(
                text("SELECT avatar_file_id FROM users WHERE avatar_file_id IS NOT NULL")
            ).scalars().all()
            if value is not None
        }

    def _file_ids(self, db: Session) -> set[int]:
        """Return stored files that belong to resettable test/user activity.

        The reset intentionally clears uploads, generated results, gallery files and
        orphaned test files, but it keeps user accounts. Account-owned files such as
        avatars must therefore survive as well.
        """
        if not self._table_exists(db, "storage_files"):
            return set()

        preserved_file_ids = self._preserved_account_file_ids(db)
        return {
            int(value)
            for value in db.execute(text("SELECT id FROM storage_files")).scalars().all()
            if int(value) not in preserved_file_ids
        }

    def preview(self, db: Session) -> dict[str, Any]:
        active_execution_ids: list[str] = []
        active_tryon_job_ids: list[int] = []
        if self._table_exists(db, "generation_module_executions"):
            active_execution_ids = [r.public_id for r in db.query(GenerationModuleExecution).all() if str(r.status).lower() in ACTIVE_STATUSES]
        if self._table_exists(db, "tryon_jobs"):
            active_tryon_job_ids = [r.id for r in db.query(TryOnJob).all() if str(r.status).lower() in ACTIVE_STATUSES]
        file_ids = self._file_ids(db)
        preserved_account_file_ids = self._preserved_account_file_ids(db)
        token_balance = int(db.execute(text("SELECT COALESCE(SUM(token_balance), 0) FROM users")).scalar() or 0)
        counts = {
            "generation_module_executions": self._count(db, "generation_module_executions"),
            "legacy_generation_jobs": self._count(db, "tryon_jobs"),
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
            "user_gallery_items": self._count(db, "user_gallery_items"),
            "finance_withdrawals": self._count(db, "finance_withdrawals"),
            "infrastructure_funding_movements": self._count(db, "infrastructure_funding_movements"),
            "infrastructure_funding_allocations": self._count(db, "infrastructure_funding_allocations"),
            "infrastructure_provider_credit_releases": self._count(db, "infrastructure_provider_credit_releases"),
            "promotional_credit_returns": self._count(db, "promotional_credit_returns"),
            "promotional_token_grants": self._count(db, "promotional_token_grants"),
            "promotional_credit_funds": self._count(db, "promotional_credit_funds"),
            "operational_expenses": self._count(db, "operational_expenses"),
            "legal_acceptances": self._count(db, "legal_acceptances"),
            "storage_files": len(file_ids),
            "account_files_preserved": len(preserved_account_file_ids),
            "tokens_to_zero": token_balance,
            "users_preserved": self._count(db, "users"),
        }
        return {
            "confirmation_text": CONFIRMATION_TEXT,
            "can_execute": not active_execution_ids and not active_tryon_job_ids,
            "active_execution_ids": active_execution_ids,
            "active_tryon_job_ids": active_tryon_job_ids,
            "counts": counts,
        }

    def execute(self, db: Session, *, confirmation: str, delete_storage_files: bool = True,
                cancel_stripe_subscriptions: bool = False,
                refund_stripe_payments: bool = False) -> dict[str, Any]:
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

        stripe_refunded = 0
        stripe_refund_failures: list[str] = []
        if refund_stripe_payments and self._table_exists(db, "billing_payments"):
            rows = db.execute(text("""
                SELECT id, provider_payment_intent_id, amount, refunded_amount
                FROM billing_payments
                WHERE provider = 'stripe'
                  AND provider_payment_intent_id IS NOT NULL
                  AND COALESCE(amount, 0) > COALESCE(refunded_amount, 0)
            """)).mappings().all()
            for row in rows:
                remaining = max(float(row["amount"] or 0) - float(row["refunded_amount"] or 0), 0.0)
                if remaining <= 0:
                    continue
                try:
                    stripe_client_service.refund_payment_intent(
                        db,
                        payment_intent_id=str(row["provider_payment_intent_id"]),
                        amount_cents=int(round(remaining * 100)),
                        reason="requested_by_customer",
                        metadata={"source": "admin_test_activity_reset", "local_payment_id": str(row["id"])},
                        idempotency_key=f"test-reset-payment-{row['id']}",
                    )
                    stripe_refunded += 1
                except Exception as exc:
                    stripe_refund_failures.append(f"{row['provider_payment_intent_id']}: {exc}")
            if stripe_refund_failures:
                raise RuntimeError("Stripe refund failed; no local data or files were deleted. " + " | ".join(stripe_refund_failures[:5]))

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

            # Purchase/legal/cash dependencies must be removed before their parents.
            delete_all("legal_acceptances")
            delete_all("finance_withdrawals")
            delete_all("infrastructure_provider_credit_releases")
            delete_all("infrastructure_funding_allocations")
            delete_all("infrastructure_funding_movements")
            delete_all("promotional_credit_returns")
            delete_all("promotional_token_grants")
            delete_all("promotional_credit_funds")
            delete_all("operational_expenses")

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

            # Generation records and gallery. "tryon_jobs" is a legacy table kept
            # for compatibility; it is not presented as a Try-On-only product anymore.
            delete_all("user_gallery_items")
            delete_all("generation_module_executions")
            delete_all("tryon_jobs")

            if delete_storage_files and file_ids and self._table_exists(db, "storage_files"):
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
            "stripe_payments_refunded": stripe_refunded,
            "completed_at": utc_now().isoformat(),
        }


generation_data_reset_service = GenerationDataResetService()
