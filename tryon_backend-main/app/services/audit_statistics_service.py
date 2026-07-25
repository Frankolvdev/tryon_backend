from datetime import timedelta

from sqlalchemy import (
    case,
    cast,
    Date,
    func,
    select,
)
from sqlalchemy.orm import Session

from app.common.time import utc_now
from app.models.audit_entry import AuditEntry
from app.schemas.audit_maintenance import (
    AuditActorMetric,
    AuditAdvancedStatisticsResponse,
    AuditDailyMetric,
    AuditGroupMetric,
)


class AuditStatisticsService:
    def advanced_statistics(
        self,
        db: Session,
        *,
        period_days: int = 30,
        top_limit: int = 10,
    ) -> AuditAdvancedStatisticsResponse:
        normalized_period = min(
            max(
                int(period_days),
                1,
            ),
            3650,
        )

        normalized_top_limit = min(
            max(
                int(top_limit),
                1,
            ),
            100,
        )

        created_from = (
            utc_now()
            - timedelta(
                days=normalized_period
            )
        )

        base_condition = (
            AuditEntry.created_at
            >= created_from
        )

        totals = db.execute(
            select(
                func.count(
                    AuditEntry.id
                ).label("total"),
                func.sum(
                    case(
                        (
                            AuditEntry.success.is_(
                                True
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ).label("successful"),
                func.sum(
                    case(
                        (
                            AuditEntry.success.is_(
                                False
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ).label("failed"),
                func.sum(
                    case(
                        (
                            AuditEntry.is_restorable.is_(
                                True
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ).label("restorable"),
                func.sum(
                    case(
                        (
                            AuditEntry.action
                            == "restore",
                            1,
                        ),
                        else_=0,
                    )
                ).label("restorations"),
            )
            .where(base_condition)
        ).mappings().one()

        total_entries = int(
            totals["total"] or 0
        )

        successful_entries = int(
            totals["successful"] or 0
        )

        failed_entries = int(
            totals["failed"] or 0
        )

        restorable_entries = int(
            totals["restorable"] or 0
        )

        restoration_entries = int(
            totals["restorations"] or 0
        )

        success_rate = (
            round(
                (
                    successful_entries
                    / total_entries
                )
                * 100,
                2,
            )
            if total_entries > 0
            else 0.0
        )

        daily_rows = db.execute(
            select(
                cast(
                    AuditEntry.created_at,
                    Date,
                ).label("day"),
                func.count(
                    AuditEntry.id
                ).label("total"),
                func.sum(
                    case(
                        (
                            AuditEntry.success.is_(
                                True
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ).label("successful"),
                func.sum(
                    case(
                        (
                            AuditEntry.success.is_(
                                False
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ).label("failed"),
                func.sum(
                    case(
                        (
                            AuditEntry.is_restorable.is_(
                                True
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ).label("restorable"),
            )
            .where(base_condition)
            .group_by(
                cast(
                    AuditEntry.created_at,
                    Date,
                )
            )
            .order_by(
                cast(
                    AuditEntry.created_at,
                    Date,
                )
            )
        ).mappings().all()

        action_rows = db.execute(
            select(
                AuditEntry.action.label("key"),
                func.count(
                    AuditEntry.id
                ).label("total"),
            )
            .where(base_condition)
            .group_by(
                AuditEntry.action
            )
            .order_by(
                func.count(
                    AuditEntry.id
                ).desc()
            )
            .limit(normalized_top_limit)
        ).mappings().all()

        entity_rows = db.execute(
            select(
                AuditEntry.entity_type.label(
                    "key"
                ),
                func.count(
                    AuditEntry.id
                ).label("total"),
            )
            .where(base_condition)
            .group_by(
                AuditEntry.entity_type
            )
            .order_by(
                func.count(
                    AuditEntry.id
                ).desc()
            )
            .limit(normalized_top_limit)
        ).mappings().all()

        actor_type_rows = db.execute(
            select(
                AuditEntry.actor_type.label(
                    "key"
                ),
                func.count(
                    AuditEntry.id
                ).label("total"),
            )
            .where(base_condition)
            .group_by(
                AuditEntry.actor_type
            )
            .order_by(
                func.count(
                    AuditEntry.id
                ).desc()
            )
            .limit(normalized_top_limit)
        ).mappings().all()

        actor_rows = db.execute(
            select(
                AuditEntry.actor_user_id,
                AuditEntry.actor_email,
                AuditEntry.actor_type,
                func.count(
                    AuditEntry.id
                ).label("total"),
                func.sum(
                    case(
                        (
                            AuditEntry.success.is_(
                                True
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ).label("successful"),
                func.sum(
                    case(
                        (
                            AuditEntry.success.is_(
                                False
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ).label("failed"),
            )
            .where(base_condition)
            .group_by(
                AuditEntry.actor_user_id,
                AuditEntry.actor_email,
                AuditEntry.actor_type,
            )
            .order_by(
                func.count(
                    AuditEntry.id
                ).desc()
            )
            .limit(normalized_top_limit)
        ).mappings().all()

        return AuditAdvancedStatisticsResponse(
            period_days=normalized_period,
            total_entries=total_entries,
            successful_entries=(
                successful_entries
            ),
            failed_entries=failed_entries,
            restorable_entries=(
                restorable_entries
            ),
            restoration_entries=(
                restoration_entries
            ),
            success_rate=success_rate,
            daily=[
                AuditDailyMetric(
                    day=row["day"],
                    total=int(
                        row["total"] or 0
                    ),
                    successful=int(
                        row["successful"] or 0
                    ),
                    failed=int(
                        row["failed"] or 0
                    ),
                    restorable=int(
                        row["restorable"] or 0
                    ),
                )
                for row in daily_rows
            ],
            top_actions=[
                AuditGroupMetric(
                    key=str(row["key"]),
                    total=int(
                        row["total"] or 0
                    ),
                )
                for row in action_rows
            ],
            top_entity_types=[
                AuditGroupMetric(
                    key=str(row["key"]),
                    total=int(
                        row["total"] or 0
                    ),
                )
                for row in entity_rows
            ],
            top_actor_types=[
                AuditGroupMetric(
                    key=str(row["key"]),
                    total=int(
                        row["total"] or 0
                    ),
                )
                for row in actor_type_rows
            ],
            top_actors=[
                AuditActorMetric(
                    actor_user_id=(
                        row["actor_user_id"]
                    ),
                    actor_email=(
                        row["actor_email"]
                    ),
                    actor_type=str(
                        row["actor_type"]
                    ),
                    total=int(
                        row["total"] or 0
                    ),
                    successful=int(
                        row["successful"] or 0
                    ),
                    failed=int(
                        row["failed"] or 0
                    ),
                )
                for row in actor_rows
            ],
            generated_at=utc_now(),
        )


audit_statistics_service = (
    AuditStatisticsService()
)