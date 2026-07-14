from sqlalchemy.orm import Session

from app.common.enums import TryOnJobStatus
from app.repositories.storage_file_repository import storage_file_repository
from app.repositories.token_transaction_repository import token_transaction_repository
from app.repositories.tryon_job_repository import tryon_job_repository
from app.repositories.user_repository import user_repository
from app.schemas.admin_dashboard import AdminDashboardResponse


class AdminDashboardService:
    def get_dashboard(self, db: Session) -> AdminDashboardResponse:
        return AdminDashboardResponse(
            total_users=user_repository.count_all(db),
            active_users=user_repository.count_active(db),
            suspended_users=user_repository.count_suspended(db),
            deleted_users=user_repository.count_deleted(db),
            total_tryon_jobs=tryon_job_repository.count_all(db),
            completed_tryon_jobs=tryon_job_repository.count_by_status(
                db,
                TryOnJobStatus.COMPLETED,
            ),
            failed_tryon_jobs=tryon_job_repository.count_by_status(
                db,
                TryOnJobStatus.FAILED,
            ),
            queued_tryon_jobs=tryon_job_repository.count_by_status(
                db,
                TryOnJobStatus.QUEUED,
            ),
            total_tokens_issued=token_transaction_repository.sum_credits(db),
            total_tokens_consumed=token_transaction_repository.sum_debits(db),
            estimated_gpu_cost_cents=tryon_job_repository.sum_estimated_gpu_cost_cents(db),
            actual_gpu_cost_cents=tryon_job_repository.sum_actual_gpu_cost_cents(db),
            total_storage_files=storage_file_repository.count_all(db),
        )


admin_dashboard_service = AdminDashboardService()