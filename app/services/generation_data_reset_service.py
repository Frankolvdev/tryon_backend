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
    """Destructive test reset for end-user generated activity only.

    The reset deliberately preserves identities and platform/admin configuration.
    It removes the commercial/creative state produced by ordinary end users and
    the derived financial test activity that would otherwise leave cashboxes dirty.
    """

    @staticmethod
    def _table_exists(db: Session, table: str) -> bool:
        return inspect(db.get_bind()).has_table(table)

    @staticmethod
    def _columns(db: Session, table: str) -> set[str]:
        if not GenerationDataResetService._table_exists(db, table):
            return set()
        return {str(row["name"]) for row in inspect(db.get_bind()).get_columns(table)}

    @staticmethod
    def _count(db: Session, table: str) -> int:
        if not GenerationDataResetService._table_exists(db, table):
            return 0
        return int(db.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar() or 0)

    @staticmethod
    def _count_for_users(db: Session, table: str, column: str, user_ids: list[int]) -> int:
        if not user_ids or not GenerationDataResetService._table_exists(db, table):
            return 0
        if column not in GenerationDataResetService._columns(db, table):
            return 0
        return int(
            db.execute(
                text(f'SELECT COUNT(*) FROM "{table}" WHERE "{column}" = ANY(:user_ids)'),
                {"user_ids": user_ids},
            ).scalar()
            or 0
        )

    @staticmethod
    def _collect_file_ids(value: Any, found: set[int]) -> None:
        if isinstance(value, str):
            raw = value.strip()
            if raw[:1] in {"{", "["}:
                try:
                    GenerationDataResetService._collect_file_ids(json.loads(raw), found)
                except (TypeError, ValueError, json.JSONDecodeError):
                    pass
            return
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

    def _final_user_ids(self, db: Session) -> list[int]:
        """Ordinary customer accounts only; owner/admin/superadmin are never reset."""
        if not self._table_exists(db, "users"):
            return []
        return [
            int(value)
            for value in db.execute(
                text(
                    """
                    SELECT id
                    FROM users
                    WHERE LOWER(COALESCE(role, 'user')) = 'user'
                      AND COALESCE(is_superuser, FALSE) = FALSE
                    ORDER BY id
                    """
                )
            ).scalars().all()
        ]

    def _target_generation_execution_rows(self, db: Session, user_ids: list[int]):
        if not self._table_exists(db, "generation_module_executions"):
            return []
        rows = db.query(GenerationModuleExecution).all()
        targets = []
        final_user_ids = set(user_ids)
        for row in rows:
            try:
                snapshot = json.loads(row.snapshot_json or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                snapshot = {}
            accounting_mode = str(snapshot.get("accounting_mode") or "commercial").lower()
            if row.user_id in final_user_ids or accounting_mode in {"admin_test", "owner_private"}:
                targets.append(row)
        return targets

    def _preserved_account_file_ids(self, db: Session) -> set[int]:
        """Identity-level files survive because user accounts survive."""
        if not self._table_exists(db, "users"):
            return set()
        return {
            int(value)
            for value in db.execute(
                text("SELECT avatar_file_id FROM users WHERE avatar_file_id IS NOT NULL")
            ).scalars().all()
            if value is not None
        }

    def _preserved_configuration_file_ids(self, db: Session) -> set[int]:
        """Files backing admin catalogs/configuration must never be treated as user test media."""
        found: set[int] = set()
        references = {
            "ancestry_media_assets": ("poster_storage_file_id", "video_storage_file_id"),
            "model_generation_assets": ("poster_storage_file_id", "video_storage_file_id"),
            "body_proportion_presets": ("preview_storage_file_id", "storage_file_id", "image_storage_file_id"),
            "bubble_butt_presets": ("preview_storage_file_id", "storage_file_id", "image_storage_file_id"),
        }
        for table, candidates in references.items():
            columns = self._columns(db, table)
            selected = [name for name in candidates if name in columns]
            if not selected:
                continue
            for column in selected:
                values = db.execute(
                    text(f'SELECT "{column}" FROM "{table}" WHERE "{column}" IS NOT NULL')
                ).scalars().all()
                found.update(int(value) for value in values if value is not None)

            for json_column in ("preview_storage_json", "generation_metadata_json", "metadata_json"):
                if json_column not in columns:
                    continue
                for value in db.execute(text(f'SELECT "{json_column}" FROM "{table}"')).scalars().all():
                    self._collect_file_ids(value, found)
        return found

    def _activity_file_ids(self, db: Session, user_ids: list[int]) -> set[int]:
        """Physical files attributable to ordinary end-user creative activity.

        User-owned storage is the primary source. Snapshot/draft/FK scanning is an
        extra safety net for old rows whose ownership may be null. Admin/catalog
        references and account avatars are subtracted at the end.
        """
        if not self._table_exists(db, "storage_files"):
            return set()

        found: set[int] = set()
        if user_ids:
            found.update(
                int(value)
                for value in db.execute(
                    text("SELECT id FROM storage_files WHERE user_id = ANY(:user_ids)"),
                    {"user_ids": user_ids},
                ).scalars().all()
            )

        for execution_row in self._target_generation_execution_rows(db, user_ids):
            self._collect_file_ids(execution_row.snapshot_json, found)

        if self._table_exists(db, "ai_model_profiles"):
            for draft in db.execute(
                text("SELECT draft_json FROM ai_model_profiles WHERE user_id = ANY(:user_ids)"),
                {"user_ids": user_ids},
            ).scalars().all():
                self._collect_file_ids(draft, found)

        fk_sources = {
            "tryon_jobs": ("person_image_file_id", "item_image_file_id", "result_file_id"),
            "user_gallery_items": ("source_file_id", "result_file_id"),
        }
        for table, candidates in fk_sources.items():
            columns = self._columns(db, table)
            user_column = "user_id" if "user_id" in columns else None
            if user_column is None:
                continue
            for column in candidates:
                if column not in columns:
                    continue
                values = db.execute(
                    text(
                        f'SELECT "{column}" FROM "{table}" '
                        f'WHERE "{user_column}" = ANY(:user_ids) AND "{column}" IS NOT NULL'
                    ),
                    {"user_ids": user_ids},
                ).scalars().all()
                found.update(int(value) for value in values if value is not None)

        preserved = self._preserved_account_file_ids(db) | self._preserved_configuration_file_ids(db)
        return {value for value in found if value not in preserved}

    def _active_generation_ids(self, db: Session, user_ids: list[int]) -> tuple[list[str], list[int]]:
        active_execution_ids: list[str] = []
        active_tryon_job_ids: list[int] = []
        if self._table_exists(db, "generation_module_executions"):
            rows = self._target_generation_execution_rows(db, user_ids)
            active_execution_ids = [r.public_id for r in rows if str(r.status).lower() in ACTIVE_STATUSES]
        if user_ids and self._table_exists(db, "tryon_jobs"):
            rows = db.query(TryOnJob).filter(TryOnJob.user_id.in_(user_ids)).all()
            active_tryon_job_ids = [r.id for r in rows if str(r.status).lower() in ACTIVE_STATUSES]
        return active_execution_ids, active_tryon_job_ids

    def preview(self, db: Session) -> dict[str, Any]:
        user_ids = self._final_user_ids(db)
        active_execution_ids, active_tryon_job_ids = self._active_generation_ids(db, user_ids)
        file_ids = self._activity_file_ids(db, user_ids)
        preserved_account_file_ids = self._preserved_account_file_ids(db)
        preserved_configuration_file_ids = self._preserved_configuration_file_ids(db)
        token_balance = 0
        if user_ids:
            token_balance = int(
                db.execute(
                    text("SELECT COALESCE(SUM(token_balance), 0) FROM users WHERE id = ANY(:user_ids)"),
                    {"user_ids": user_ids},
                ).scalar()
                or 0
            )

        counts = {
            "end_users_targeted": len(user_ids),
            "ai_model_profiles": self._count_for_users(db, "ai_model_profiles", "user_id", user_ids),
            "generation_module_executions": len(self._target_generation_execution_rows(db, user_ids)),
            "legacy_generation_jobs": self._count_for_users(db, "tryon_jobs", "user_id", user_ids),
            "generation_financial_records": self._count_for_users(db, "generation_financial_records", "user_id", user_ids),
            "token_consumption_allocations": self._count_for_users(db, "token_consumption_allocations", "user_id", user_ids),
            "token_transactions": self._count_for_users(db, "token_transactions", "user_id", user_ids),
            "token_value_lots": self._count_for_users(db, "token_value_lots", "user_id", user_ids),
            "token_purchases": self._count_for_users(db, "token_purchases", "user_id", user_ids),
            "billing_payments": self._count_for_users(db, "billing_payments", "user_id", user_ids),
            "billing_invoices": self._count_for_users(db, "billing_invoices", "user_id", user_ids),
            "user_subscriptions": self._count_for_users(db, "user_subscriptions", "user_id", user_ids),
            "billing_customers": self._count_for_users(db, "billing_customers", "user_id", user_ids),
            "user_gallery_items": self._count_for_users(db, "user_gallery_items", "user_id", user_ids),
            "user_notifications": self._count_for_users(db, "user_notifications", "recipient_user_id", user_ids),
            "support_tickets": self._count_for_users(db, "support_tickets", "user_id", user_ids),
            # These are derived test-finance/event ledgers, not platform configuration.
            "billing_events": self._count(db, "billing_events"),
            "finance_withdrawals": self._count(db, "finance_withdrawals"),
            "infrastructure_funding_movements": self._count(db, "infrastructure_funding_movements"),
            "infrastructure_funding_allocations": self._count(db, "infrastructure_funding_allocations"),
            "infrastructure_provider_credit_releases": self._count(db, "infrastructure_provider_credit_releases"),
            "promotional_credit_returns": self._count(db, "promotional_credit_returns"),
            "promotional_token_grants": self._count(db, "promotional_token_grants"),
            "promotional_funding_cycles": self._count(db, "promotional_funding_cycles"),
            "promotional_credit_funds": self._count(db, "promotional_credit_funds"),
            "operational_expenses": self._count(db, "operational_expenses"),
            "storage_files": len(file_ids),
            "account_files_preserved": len(preserved_account_file_ids),
            "configuration_files_preserved": len(preserved_configuration_file_ids),
            "tokens_to_zero": token_balance,
            "users_preserved": self._count(db, "users"),
            "promotional_funding_sources_preserved": self._count(db, "promotional_funding_sources"),
        }
        return {
            "confirmation_text": CONFIRMATION_TEXT,
            "can_execute": not active_execution_ids and not active_tryon_job_ids,
            "active_execution_ids": active_execution_ids,
            "active_tryon_job_ids": active_tryon_job_ids,
            "counts": counts,
        }

    def execute(
        self,
        db: Session,
        *,
        confirmation: str,
        delete_storage_files: bool = True,
        cancel_stripe_subscriptions: bool = False,
        refund_stripe_payments: bool = False,
    ) -> dict[str, Any]:
        if confirmation.strip() != CONFIRMATION_TEXT:
            raise ValueError(f"Confirmation must exactly match: {CONFIRMATION_TEXT}")

        user_ids = self._final_user_ids(db)
        preview = self.preview(db)
        if not preview["can_execute"]:
            raise RuntimeError("There are active end-user generations. Cancel or finish them before resetting activity.")

        # External effects are scoped to ordinary end users only. Admin/owner Stripe
        # activity is never touched by this maintenance action.
        stripe_cancelled = 0
        stripe_failures: list[str] = []
        if cancel_stripe_subscriptions and user_ids and self._table_exists(db, "user_subscriptions"):
            rows = db.execute(
                text(
                    "SELECT provider_subscription_id FROM user_subscriptions "
                    "WHERE user_id = ANY(:user_ids) AND provider_subscription_id IS NOT NULL"
                ),
                {"user_ids": user_ids},
            ).all()
            for (subscription_id,) in rows:
                try:
                    stripe_client_service.cancel_subscription_immediately(
                        db, subscription_id=subscription_id, invoice_now=False, prorate=False
                    )
                    stripe_cancelled += 1
                except Exception as exc:
                    stripe_failures.append(f"{subscription_id}: {exc}")
            if stripe_failures:
                raise RuntimeError(
                    "Stripe cancellation failed; no local data was deleted. " + " | ".join(stripe_failures[:5])
                )

        stripe_refunded = 0
        stripe_refund_failures: list[str] = []
        if refund_stripe_payments and user_ids and self._table_exists(db, "billing_payments"):
            rows = db.execute(
                text(
                    """
                    SELECT id, provider_payment_intent_id, amount, refunded_amount
                    FROM billing_payments
                    WHERE user_id = ANY(:user_ids)
                      AND provider = 'stripe'
                      AND provider_payment_intent_id IS NOT NULL
                      AND COALESCE(amount, 0) > COALESCE(refunded_amount, 0)
                    """
                ),
                {"user_ids": user_ids},
            ).mappings().all()
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
                raise RuntimeError(
                    "Stripe refund failed; no local data or files were deleted. "
                    + " | ".join(stripe_refund_failures[:5])
                )

        file_ids = self._activity_file_ids(db, user_ids)
        storage_rows = db.query(StorageFile).filter(StorageFile.id.in_(file_ids)).all() if file_ids else []
        deleted_storage_files = 0
        storage_failures: list[str] = []
        if delete_storage_files:
            for row in storage_rows:
                try:
                    storage_service.delete_file(db=db, storage_file=row)
                    deleted_storage_files += 1
                except Exception as exc:
                    storage_failures.append(f"{row.id} ({row.provider}/{row.object_key}): {exc}")
            if storage_failures:
                raise RuntimeError(
                    "Storage cleanup failed; database activity was not deleted. "
                    + " | ".join(storage_failures[:5])
                )

        deleted: dict[str, int] = {}

        def delete_all(table: str) -> None:
            if self._table_exists(db, table):
                result = db.execute(text(f'DELETE FROM "{table}"'))
                deleted[table] = int(result.rowcount or 0)

        def delete_for_users(table: str, column: str = "user_id") -> None:
            if not user_ids or not self._table_exists(db, table) or column not in self._columns(db, table):
                deleted.setdefault(table, 0)
                return
            result = db.execute(
                text(f'DELETE FROM "{table}" WHERE "{column}" = ANY(:user_ids)'),
                {"user_ids": user_ids},
            )
            deleted[table] = int(result.rowcount or 0)

        def ids_for_users(table: str, column: str = "user_id") -> list[int]:
            if not user_ids or not self._table_exists(db, table) or column not in self._columns(db, table):
                return []
            return [
                int(value)
                for value in db.execute(
                    text(f'SELECT id FROM "{table}" WHERE "{column}" = ANY(:user_ids)'),
                    {"user_ids": user_ids},
                ).scalars().all()
            ]

        try:
            target_generation_rows = self._target_generation_execution_rows(db, user_ids)
            target_generation_public_ids = [row.public_id for row in target_generation_rows]
            lot_ids = ids_for_users("token_value_lots")
            transaction_ids = ids_for_users("token_transactions")
            purchase_ids = ids_for_users("token_purchases")
            payment_ids = ids_for_users("billing_payments")
            user_background_job_ids = ids_for_users("background_jobs")

            external_job_ids: list[int] = []
            if user_background_job_ids and self._table_exists(db, "background_jobs"):
                external_job_ids = [
                    int(value)
                    for value in db.execute(
                        text(
                            "SELECT DISTINCT external_ai_job_id FROM background_jobs "
                            "WHERE id = ANY(:ids) AND external_ai_job_id IS NOT NULL"
                        ),
                        {"ids": user_background_job_ids},
                    ).scalars().all()
                ]

            # User notification state is activity, while notification settings and
            # push registrations are account configuration and remain untouched.
            delete_for_users("user_notification_receipts")
            delete_for_users("user_notifications", "recipient_user_id")
            delete_for_users("support_tickets")

            # Background execution children first, and only jobs owned by target users.
            if user_background_job_ids:
                if self._table_exists(db, "background_job_attempts"):
                    result = db.execute(
                        text("DELETE FROM background_job_attempts WHERE background_job_id = ANY(:ids)"),
                        {"ids": user_background_job_ids},
                    )
                    deleted["background_job_attempts"] = int(result.rowcount or 0)
                if self._table_exists(db, "background_job_dependencies"):
                    dep_columns = self._columns(db, "background_job_dependencies")
                    if "depends_on_job_id" in dep_columns:
                        result = db.execute(
                            text(
                                "DELETE FROM background_job_dependencies "
                                "WHERE background_job_id = ANY(:ids) OR depends_on_job_id = ANY(:ids)"
                            ),
                            {"ids": user_background_job_ids},
                        )
                    else:
                        result = db.execute(
                            text("DELETE FROM background_job_dependencies WHERE background_job_id = ANY(:ids)"),
                            {"ids": user_background_job_ids},
                        )
                    deleted["background_job_dependencies"] = int(result.rowcount or 0)
                result = db.execute(
                    text("DELETE FROM background_jobs WHERE id = ANY(:ids)"),
                    {"ids": user_background_job_ids},
                )
                deleted["background_jobs"] = int(result.rowcount or 0)
            if external_job_ids and self._table_exists(db, "external_ai_jobs"):
                # Do not delete a shared external job if a surviving background job still references it.
                result = db.execute(
                    text(
                        "DELETE FROM external_ai_jobs WHERE id = ANY(:ids) "
                        "AND NOT EXISTS (SELECT 1 FROM background_jobs b WHERE b.external_ai_job_id = external_ai_jobs.id)"
                    ),
                    {"ids": external_job_ids},
                )
                deleted["external_ai_jobs"] = int(result.rowcount or 0)

            # Purchase checkout acceptances are activity; account/TOS acceptances survive.
            if self._table_exists(db, "legal_acceptances") and user_ids:
                result = db.execute(
                    text(
                        """
                        DELETE FROM legal_acceptances
                        WHERE user_id = ANY(:user_ids)
                          AND (
                              context IN ('token_checkout', 'subscription_checkout')
                              OR token_purchase_id IS NOT NULL
                              OR billing_payment_id IS NOT NULL
                              OR token_bag_id IS NOT NULL
                          )
                        """
                    ),
                    {"user_ids": user_ids},
                )
                deleted["legal_acceptances"] = int(result.rowcount or 0)

            # Cashbox/financial test activity is derived from user commercial activity.
            # It is cleared globally so the preserved platform configuration starts clean.
            delete_all("finance_withdrawals")
            delete_all("infrastructure_provider_credit_releases")
            delete_all("infrastructure_funding_allocations")
            delete_all("infrastructure_funding_movements")
            delete_all("promotional_credit_returns")
            delete_all("promotional_token_grants")
            delete_all("promotional_funding_cycles")
            # Preserve promotional_funding_sources: recurrence/provider policy is configuration.
            delete_all("promotional_credit_funds")
            delete_all("operational_expenses")

            # User finance/token ledger dependencies.
            delete_for_users("token_consumption_allocations")
            if target_generation_public_ids and self._table_exists(db, "generation_financial_records"):
                result = db.execute(
                    text("DELETE FROM generation_financial_records WHERE execution_id = ANY(:execution_ids)"),
                    {"execution_ids": target_generation_public_ids},
                )
                deleted["generation_financial_records"] = int(result.rowcount or 0)
                # Also remove any remaining user-scoped records not tied to a persisted execution.
                if user_ids:
                    result = db.execute(
                        text("DELETE FROM generation_financial_records WHERE user_id = ANY(:user_ids)"),
                        {"user_ids": user_ids},
                    )
                    deleted["generation_financial_records"] += int(result.rowcount or 0)
            else:
                delete_for_users("generation_financial_records")
            delete_for_users("billing_invoices")
            delete_for_users("token_purchases")
            delete_for_users("billing_payments")
            delete_for_users("user_subscriptions")
            delete_for_users("token_transactions")
            delete_for_users("token_value_lots")
            delete_for_users("billing_customers")
            # Billing events contain remote commercial webhook payloads and are not configuration.
            delete_all("billing_events")

            # Creative/user-generated records. Admin catalogs and generation-module definitions survive.
            delete_for_users("user_gallery_items")
            delete_for_users("ai_model_profiles")
            target_execution_ids = [row.id for row in target_generation_rows]
            if target_execution_ids:
                result = db.execute(
                    text("DELETE FROM generation_module_executions WHERE id = ANY(:ids)"),
                    {"ids": target_execution_ids},
                )
                deleted["generation_module_executions"] = int(result.rowcount or 0)
            else:
                deleted["generation_module_executions"] = 0
            delete_for_users("tryon_jobs")

            if delete_storage_files and file_ids and self._table_exists(db, "storage_files"):
                result = db.execute(
                    text("DELETE FROM storage_files WHERE id = ANY(:ids)"),
                    {"ids": list(file_ids)},
                )
                deleted["storage_files"] = int(result.rowcount or 0)

            # Preserve every account, including ordinary users; only their commercial wallet resets.
            zeroed_users = 0
            if user_ids:
                result = db.execute(
                    text("UPDATE users SET token_balance = 0 WHERE id = ANY(:user_ids) AND token_balance <> 0"),
                    {"user_ids": user_ids},
                )
                zeroed_users = int(result.rowcount or 0)

            db.commit()
        except Exception:
            db.rollback()
            raise

        return {
            "success": True,
            "targeted_end_users": len(user_ids),
            "deleted": deleted,
            "deleted_storage_files": deleted_storage_files,
            "zeroed_users": zeroed_users,
            "stripe_subscriptions_cancelled": stripe_cancelled,
            "stripe_payments_refunded": stripe_refunded,
            "completed_at": utc_now().isoformat(),
        }


generation_data_reset_service = GenerationDataResetService()
