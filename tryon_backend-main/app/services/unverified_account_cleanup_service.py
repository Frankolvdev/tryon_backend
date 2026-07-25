import logging
from datetime import timedelta

from sqlalchemy import (
    func,
    select,
    update,
)
from sqlalchemy.orm import Session

from app.common.enums import (
    UserStatus,
)
from app.common.time import utc_now
from app.models.account_verification_challenge import (
    AccountVerificationChallenge,
)
from app.models.user import User
from app.models.user_account_security import (
    UserAccountSecurity,
)
from app.schemas.account_security import (
    UnverifiedAccountListResponse,
    UnverifiedAccountResponse,
    UnverifiedCleanupResponse,
)
from app.services.account_security_service import (
    account_security_service,
)
from app.services.auth_service import (
    auth_service,
)


logger = logging.getLogger(
    "app.unverified_account_cleanup"
)


class UnverifiedAccountCleanupService:
    def _cutoff(
        self,
        db: Session,
    ):
        settings = (
            account_security_service
            .get_or_create_settings(db)
        )

        cutoff = (
            utc_now()
            - timedelta(
                days=(
                    settings
                    .delete_unverified_accounts_after_days
                )
            )
        )

        return settings, cutoff

    def _base_statement(
        self,
        *,
        cutoff,
        eligible_only: bool,
    ):
        statement = (
            select(
                User,
                UserAccountSecurity,
            )
            .join(
                UserAccountSecurity,
                UserAccountSecurity.user_id
                == User.id,
            )
            .where(
                UserAccountSecurity
                .email_verified
                .is_(False),
                UserAccountSecurity
                .account_status
                == "pending_verification",
                User.deleted_at.is_(None),
            )
        )

        if eligible_only:
            statement = statement.where(
                User.created_at <= cutoff
            )

        return statement

    def list_unverified_accounts(
        self,
        db: Session,
        *,
        eligible_only: bool = False,
        skip: int = 0,
        limit: int = 100,
    ) -> UnverifiedAccountListResponse:
        settings, cutoff = self._cutoff(
            db
        )

        statement = (
            self._base_statement(
                cutoff=cutoff,
                eligible_only=(
                    eligible_only
                ),
            )
            .order_by(
                User.created_at.asc()
            )
            .offset(skip)
            .limit(limit)
        )

        rows = db.execute(
            statement
        ).all()

        count_statement = (
            select(
                func.count(User.id)
            )
            .join(
                UserAccountSecurity,
                UserAccountSecurity.user_id
                == User.id,
            )
            .where(
                UserAccountSecurity
                .email_verified
                .is_(False),
                UserAccountSecurity
                .account_status
                == "pending_verification",
                User.deleted_at.is_(None),
            )
        )

        if eligible_only:
            count_statement = (
                count_statement.where(
                    User.created_at <= cutoff
                )
            )

        total = int(
            db.execute(
                count_statement
            ).scalar_one()
        )

        now = utc_now()
        days = (
            settings
            .delete_unverified_accounts_after_days
        )

        items = [
            UnverifiedAccountResponse(
                user_id=user.id,
                email=user.email,
                account_status=(
                    security.account_status
                ),
                email_verified=(
                    security.email_verified
                ),
                created_at=user.created_at,
                eligible_for_cleanup_at=(
                    user.created_at
                    + timedelta(days=days)
                ),
                is_eligible_for_cleanup=(
                    user.created_at <= cutoff
                    and now >= (
                        user.created_at
                        + timedelta(days=days)
                    )
                ),
            )
            for user, security in rows
        ]

        return UnverifiedAccountListResponse(
            items=items,
            total=total,
            cleanup_after_days=days,
            skip=skip,
            limit=limit,
        )

    def cleanup(
        self,
        db: Session,
        *,
        dry_run: bool = True,
        limit: int = 500,
    ) -> UnverifiedCleanupResponse:
        _, cutoff = self._cutoff(
            db
        )

        statement = (
            self._base_statement(
                cutoff=cutoff,
                eligible_only=True,
            )
            .order_by(
                User.created_at.asc()
            )
            .limit(limit)
        )

        rows = db.execute(
            statement
        ).all()

        scanned = len(rows)
        eligible = len(rows)

        user_ids = [
            user.id
            for user, _ in rows
        ]

        if dry_run or not rows:
            return UnverifiedCleanupResponse(
                success=True,
                dry_run=dry_run,
                cutoff_at=cutoff,
                scanned=scanned,
                eligible=eligible,
                deactivated=0,
                challenges_cancelled=0,
                sessions_revoked=0,
                user_ids=user_ids,
                message=(
                    "Cleanup simulation completed."
                    if dry_run
                    else (
                        "No eligible unverified "
                        "accounts were found."
                    )
                ),
            )

        now = utc_now()
        deactivated = 0
        sessions_revoked = 0

        for user, security in rows:
            user.is_active = False
            user.status = (
                UserStatus.INACTIVE.value
            )

            user.deleted_at = now

            security.account_status = (
                "deleted_unverified"
            )

            security.locked_until = None

            db.add(user)
            db.add(security)

            sessions_revoked += (
                auth_service
                .revoke_all_user_sessions(
                    db,
                    user_id=user.id,
                )
            )

            deactivated += 1

        challenges_result = db.execute(
            update(
                AccountVerificationChallenge
            )
            .where(
                AccountVerificationChallenge
                .user_id
                .in_(user_ids),
                AccountVerificationChallenge
                .status
                == "pending",
            )
            .values(
                status="cancelled",
            )
        )

        challenges_cancelled = int(
            challenges_result.rowcount or 0
        )

        db.commit()

        logger.info(
            "Unverified account cleanup completed.",
            extra={
                "cutoff_at": cutoff.isoformat(),
                "deactivated": deactivated,
                "challenges_cancelled": (
                    challenges_cancelled
                ),
                "sessions_revoked": (
                    sessions_revoked
                ),
            },
        )

        return UnverifiedCleanupResponse(
            success=True,
            dry_run=False,
            cutoff_at=cutoff,
            scanned=scanned,
            eligible=eligible,
            deactivated=deactivated,
            challenges_cancelled=(
                challenges_cancelled
            ),
            sessions_revoked=(
                sessions_revoked
            ),
            user_ids=user_ids,
            message=(
                "Eligible unverified accounts "
                "were deactivated successfully."
            ),
        )


unverified_account_cleanup_service = (
    UnverifiedAccountCleanupService()
)