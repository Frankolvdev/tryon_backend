from datetime import datetime

from sqlalchemy import (
    func,
    select,
    update,
)
from sqlalchemy.orm import Session

from app.models.account_security_setting import (
    AccountSecuritySetting,
)
from app.models.account_verification_challenge import (
    AccountVerificationChallenge,
)
from app.models.user import User
from app.models.user_account_security import (
    UserAccountSecurity,
)


class AccountSecurityRepository:
    def get_settings(
        self,
        db: Session,
    ) -> AccountSecuritySetting | None:
        return db.get(
            AccountSecuritySetting,
            1,
        )

    def get_user_by_email(
        self,
        db: Session,
        *,
        email: str,
    ) -> User | None:
        statement = select(
            User
        ).where(
            func.lower(User.email)
            == email.lower()
        )

        return db.execute(
            statement
        ).scalar_one_or_none()

    def get_user_by_id(
        self,
        db: Session,
        *,
        user_id: int,
    ) -> User | None:
        return db.get(
            User,
            user_id,
        )

    def get_user_security(
        self,
        db: Session,
        *,
        user_id: int,
    ) -> UserAccountSecurity | None:
        statement = select(
            UserAccountSecurity
        ).where(
            UserAccountSecurity.user_id
            == user_id
        )

        return db.execute(
            statement
        ).scalar_one_or_none()

    def get_active_challenge(
        self,
        db: Session,
        *,
        email: str,
        purpose: str,
    ) -> AccountVerificationChallenge | None:
        statement = (
            select(
                AccountVerificationChallenge
            )
            .where(
                func.lower(
                    AccountVerificationChallenge.email
                )
                == email.lower(),
                AccountVerificationChallenge.purpose
                == purpose,
                AccountVerificationChallenge.status
                == "pending",
            )
            .order_by(
                AccountVerificationChallenge
                .created_at
                .desc()
            )
            .limit(1)
        )

        return db.execute(
            statement
        ).scalar_one_or_none()

    def get_challenge_by_id(
        self,
        db: Session,
        *,
        challenge_id: int,
    ) -> AccountVerificationChallenge | None:
        return db.get(
            AccountVerificationChallenge,
            challenge_id,
        )

    def count_challenges_since(
        self,
        db: Session,
        *,
        email: str,
        purpose: str,
        created_from: datetime,
    ) -> int:
        statement = select(
            func.count(
                AccountVerificationChallenge.id
            )
        ).where(
            func.lower(
                AccountVerificationChallenge.email
            )
            == email.lower(),
            AccountVerificationChallenge.purpose
            == purpose,
            AccountVerificationChallenge.created_at
            >= created_from,
        )

        return int(
            db.execute(
                statement
            ).scalar_one()
        )

    def list_challenges(
        self,
        db: Session,
        *,
        user_id: int | None = None,
        email: str | None = None,
        purpose: str | None = None,
        status: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[AccountVerificationChallenge]:
        statement = select(
            AccountVerificationChallenge
        )

        if user_id is not None:
            statement = statement.where(
                AccountVerificationChallenge.user_id
                == user_id
            )

        if email:
            statement = statement.where(
                func.lower(
                    AccountVerificationChallenge.email
                )
                == email.lower()
            )

        if purpose:
            statement = statement.where(
                AccountVerificationChallenge.purpose
                == purpose
            )

        if status:
            statement = statement.where(
                AccountVerificationChallenge.status
                == status
            )

        statement = (
            statement
            .order_by(
                AccountVerificationChallenge
                .created_at
                .desc()
            )
            .offset(skip)
            .limit(limit)
        )

        return list(
            db.execute(
                statement
            ).scalars().all()
        )

    def count_challenges(
        self,
        db: Session,
        *,
        user_id: int | None = None,
        email: str | None = None,
        purpose: str | None = None,
        status: str | None = None,
    ) -> int:
        statement = select(
            func.count(
                AccountVerificationChallenge.id
            )
        )

        if user_id is not None:
            statement = statement.where(
                AccountVerificationChallenge.user_id
                == user_id
            )

        if email:
            statement = statement.where(
                func.lower(
                    AccountVerificationChallenge.email
                )
                == email.lower()
            )

        if purpose:
            statement = statement.where(
                AccountVerificationChallenge.purpose
                == purpose
            )

        if status:
            statement = statement.where(
                AccountVerificationChallenge.status
                == status
            )

        return int(
            db.execute(
                statement
            ).scalar_one()
        )

    def cancel_pending_challenges(
        self,
        db: Session,
        *,
        email: str,
        purpose: str | None = None,
    ) -> int:
        statement = (
            update(
                AccountVerificationChallenge
            )
            .where(
                func.lower(
                    AccountVerificationChallenge.email
                )
                == email.lower(),
                AccountVerificationChallenge.status
                == "pending",
            )
        )

        if purpose:
            statement = statement.where(
                AccountVerificationChallenge.purpose
                == purpose
            )

        result = db.execute(
            statement.values(
                status="cancelled",
            )
        )

        return int(
            result.rowcount or 0
        )


account_security_repository = (
    AccountSecurityRepository()
)