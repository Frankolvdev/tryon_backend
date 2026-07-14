import csv
from pathlib import Path
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.config import settings
from app.repositories.audit_log_repository import audit_log_repository
from app.repositories.storage_file_repository import storage_file_repository
from app.repositories.token_transaction_repository import token_transaction_repository
from app.repositories.tryon_job_repository import tryon_job_repository
from app.repositories.user_repository import user_repository
from app.schemas.report import ReportResponse


class ReportService:
    def _reports_dir(self) -> Path:
        reports_dir = Path(settings.LOCAL_STORAGE_DIR) / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        return reports_dir

    def _create_csv_report(
        self,
        *,
        report_name: str,
        headers: list[str],
        rows: list[list],
    ) -> ReportResponse:
        filename = f"{report_name}_{uuid4().hex}.csv"
        path = self._reports_dir() / filename

        with path.open("w", newline="", encoding="utf-8") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(headers)
            writer.writerows(rows)

        return ReportResponse(
            report_name=report_name,
            download_url=f"/local-files/reports/{filename}",
        )

    def users_report(self, db: Session) -> ReportResponse:
        users = user_repository.list_users(
            db,
            skip=0,
            limit=10000,
            include_deleted=True,
        )

        return self._create_csv_report(
            report_name="users",
            headers=[
                "id",
                "email",
                "full_name",
                "role",
                "status",
                "is_active",
                "is_verified",
                "token_balance",
                "created_at",
                "deleted_at",
            ],
            rows=[
                [
                    user.id,
                    user.email,
                    user.full_name,
                    user.role,
                    user.status,
                    user.is_active,
                    user.is_verified,
                    user.token_balance,
                    user.created_at,
                    user.deleted_at,
                ]
                for user in users
            ],
        )

    def tryon_jobs_report(self, db: Session) -> ReportResponse:
        jobs = tryon_job_repository.list_all(
            db,
            skip=0,
            limit=10000,
        )

        return self._create_csv_report(
            report_name="tryon_jobs",
            headers=[
                "id",
                "user_id",
                "status",
                "item_type",
                "quality_mode",
                "tokens_cost",
                "estimated_gpu_seconds",
                "estimated_gpu_cost_cents",
                "actual_gpu_seconds",
                "actual_gpu_cost_cents",
                "runpod_job_id",
                "created_at",
                "completed_at",
            ],
            rows=[
                [
                    job.id,
                    job.user_id,
                    job.status,
                    job.item_type,
                    job.quality_mode,
                    job.tokens_cost,
                    job.estimated_gpu_seconds,
                    job.estimated_gpu_cost_cents,
                    job.actual_gpu_seconds,
                    job.actual_gpu_cost_cents,
                    job.runpod_job_id,
                    job.created_at,
                    job.completed_at,
                ]
                for job in jobs
            ],
        )

    def token_transactions_report(self, db: Session) -> ReportResponse:
        transactions = token_transaction_repository.get_all(
            db,
            skip=0,
            limit=10000,
        )

        return self._create_csv_report(
            report_name="token_transactions",
            headers=[
                "id",
                "user_id",
                "transaction_type",
                "amount",
                "balance_after",
                "source",
                "reference_id",
                "description",
                "created_at",
            ],
            rows=[
                [
                    transaction.id,
                    transaction.user_id,
                    transaction.transaction_type,
                    transaction.amount,
                    transaction.balance_after,
                    transaction.source,
                    transaction.reference_id,
                    transaction.description,
                    transaction.created_at,
                ]
                for transaction in transactions
            ],
        )

    def storage_files_report(self, db: Session) -> ReportResponse:
        files = storage_file_repository.list_all(
            db,
            skip=0,
            limit=10000,
        )

        return self._create_csv_report(
            report_name="storage_files",
            headers=[
                "id",
                "user_id",
                "provider",
                "object_key",
                "public_url",
                "original_filename",
                "content_type",
                "size_bytes",
                "created_at",
            ],
            rows=[
                [
                    file_obj.id,
                    file_obj.user_id,
                    file_obj.provider,
                    file_obj.object_key,
                    file_obj.public_url,
                    file_obj.original_filename,
                    file_obj.content_type,
                    file_obj.size_bytes,
                    file_obj.created_at,
                ]
                for file_obj in files
            ],
        )

    def audit_logs_report(self, db: Session) -> ReportResponse:
        logs = audit_log_repository.list_all(
            db,
            skip=0,
            limit=10000,
        )

        return self._create_csv_report(
            report_name="audit_logs",
            headers=[
                "id",
                "actor_user_id",
                "action",
                "entity_type",
                "entity_id",
                "description",
                "ip_address",
                "user_agent",
                "created_at",
            ],
            rows=[
                [
                    log.id,
                    log.actor_user_id,
                    log.action,
                    log.entity_type,
                    log.entity_id,
                    log.description,
                    log.ip_address,
                    log.user_agent,
                    log.created_at,
                ]
                for log in logs
            ],
        )


report_service = ReportService()