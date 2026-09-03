from sqlalchemy.orm import Session

from app.common.enums import ScheduledJobStatus
from app.repositories.scheduled_job_repository import scheduled_job_repository
from app.schemas.scheduler import ScheduledJobCreate
from app.services.scheduler_service import scheduler_service


class DefaultSchedulerJobsService:
    def _create_if_missing(
        self,
        db: Session,
        data: ScheduledJobCreate,
    ) -> None:
        existing = scheduled_job_repository.get_by_key(db, data.key)

        if existing:
            return

        scheduler_service.create_job(db=db, data=data)

    def seed_defaults(self, db: Session) -> dict:
        jobs = [
            ScheduledJobCreate(
                key="daily_health_check",
                name="Daily Health Check",
                description="Checks core system health every day.",
                cron_expression="0 8 * * *",
                status=ScheduledJobStatus.ACTIVE,
                is_system=True,
            ),
            ScheduledJobCreate(
                key="cleanup_old_notifications",
                name="Cleanup Old Notifications",
                description="Deletes old admin notifications.",
                cron_expression="0 3 * * *",
                status=ScheduledJobStatus.ACTIVE,
                is_system=True,
            ),
            ScheduledJobCreate(
                key="cleanup_old_activity_logs",
                name="Cleanup Old Activity Logs",
                description="Deletes old activity logs according to retention settings.",
                cron_expression="30 3 * * *",
                status=ScheduledJobStatus.ACTIVE,
                is_system=True,
            ),
            ScheduledJobCreate(
                key="cleanup_old_audit_logs",
                name="Cleanup Old Audit Logs",
                description="Deletes old audit logs according to retention settings.",
                cron_expression="0 4 * * *",
                status=ScheduledJobStatus.ACTIVE,
                is_system=True,
            ),
            ScheduledJobCreate(
                key="generate_daily_analytics",
                name="Generate Daily Analytics",
                description="Calculates daily analytics snapshots.",
                cron_expression="15 4 * * *",
                status=ScheduledJobStatus.ACTIVE,
                is_system=True,
            ),
            ScheduledJobCreate(
                key="cleanup_temp_files",
                name="Cleanup Temporary Files",
                description="Deletes temporary files and orphan local storage files.",
                cron_expression="45 4 * * *",
                status=ScheduledJobStatus.ACTIVE,
                is_system=True,
            ),
            ScheduledJobCreate(
                key="repair_stuck_tryon_jobs",
                name="Repair Stuck Try-On Jobs",
                description="Detects and repairs stuck try-on jobs.",
                cron_expression="*/30 * * * *",
                status=ScheduledJobStatus.ACTIVE,
                is_system=True,
            ),
            ScheduledJobCreate(
                key="poll_pending_runpod_jobs",
                name="Poll Pending RunPod Jobs",
                description="Polls pending RunPod Serverless jobs when callbacks are delayed or missing.",
                cron_expression="*/5 * * * *",
                status=ScheduledJobStatus.ACTIVE,
                is_system=True,
            ),
            ScheduledJobCreate(
                key="calculate_gpu_costs",
                name="Calculate GPU Costs",
                description="Calculates estimated and actual GPU costs.",
                cron_expression="0 * * * *",
                status=ScheduledJobStatus.ACTIVE,
                is_system=True,
            ),
            ScheduledJobCreate(
                key="process_pending_webhooks",
                name="Process Pending Webhooks",
                description="Retries pending or failed outgoing webhook events.",
                cron_expression="*/10 * * * *",
                status=ScheduledJobStatus.ACTIVE,
                is_system=True,
            ),
            ScheduledJobCreate(
                key="renew_subscriptions",
                name="Renew Subscriptions",
                description="Future billing job for subscription renewals.",
                cron_expression="0 * * * *",
                status=ScheduledJobStatus.PAUSED,
                is_system=True,
            ),
            ScheduledJobCreate(
                key="grant_monthly_subscription_tokens",
                name="Grant Monthly Subscription Tokens",
                description="Future billing job for granting monthly subscription tokens.",
                cron_expression="10 * * * *",
                status=ScheduledJobStatus.PAUSED,
                is_system=True,
            ),
            ScheduledJobCreate(
                key="retry_failed_webhooks",
                name="Retry Failed Webhooks",
                description="Retries failed outgoing or incoming webhook events.",
                cron_expression="*/15 * * * *",
                status=ScheduledJobStatus.ACTIVE,
                is_system=True,
            ),
            ScheduledJobCreate(
                key="sync_runpod_prices",
                name="Sync RunPod Prices",
                description="Future AI job for syncing RunPod GPU prices.",
                cron_expression="0 */6 * * *",
                status=ScheduledJobStatus.PAUSED,
                is_system=True,
            ),
        ]

        created = 0
        skipped = 0

        for job in jobs:
            existing = scheduled_job_repository.get_by_key(db, job.key)

            if existing:
                skipped += 1
                continue

            self._create_if_missing(db, job)
            created += 1

        return {
            "created": created,
            "skipped": skipped,
            "total": len(jobs),
        }


default_scheduler_jobs_service = DefaultSchedulerJobsService()