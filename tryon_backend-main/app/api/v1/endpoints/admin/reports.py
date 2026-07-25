from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.models.user import User
from app.schemas.report import ReportResponse
from app.services.report_service import report_service

router = APIRouter()


@router.post("/reports/users", response_model=ReportResponse)
def generate_users_report(
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return report_service.users_report(db)


@router.post("/reports/tryon-jobs", response_model=ReportResponse)
def generate_tryon_jobs_report(
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return report_service.tryon_jobs_report(db)


@router.post("/reports/token-transactions", response_model=ReportResponse)
def generate_token_transactions_report(
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return report_service.token_transactions_report(db)


@router.post("/reports/storage-files", response_model=ReportResponse)
def generate_storage_files_report(
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return report_service.storage_files_report(db)


@router.post("/reports/audit-logs", response_model=ReportResponse)
def generate_audit_logs_report(
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return report_service.audit_logs_report(db)