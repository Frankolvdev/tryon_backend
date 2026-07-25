from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.rate_limit_policy import RateLimitPolicy
from app.repositories.base import BaseRepository


class RateLimitPolicyRepository(
    BaseRepository[RateLimitPolicy]
):
    def __init__(self):
        super().__init__(RateLimitPolicy)

    def get_by_key(
        self,
        db: Session,
        key: str,
    ) -> RateLimitPolicy | None:
        statement = select(RateLimitPolicy).where(
            RateLimitPolicy.key == key,
        )

        return db.execute(statement).scalar_one_or_none()

    def list_enabled(
        self,
        db: Session,
    ) -> list[RateLimitPolicy]:
        statement = (
            select(RateLimitPolicy)
            .where(RateLimitPolicy.is_enabled.is_(True))
            .order_by(
                RateLimitPolicy.priority.asc(),
                RateLimitPolicy.id.asc(),
            )
        )

        return list(db.execute(statement).scalars().all())

    def list_filtered(
        self,
        db: Session,
        *,
        search: str | None = None,
        is_enabled: bool | None = None,
        scope: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[RateLimitPolicy]:
        statement = select(RateLimitPolicy)

        if search:
            pattern = f"%{search.strip()}%"

            statement = statement.where(
                or_(
                    RateLimitPolicy.key.ilike(pattern),
                    RateLimitPolicy.name.ilike(pattern),
                    RateLimitPolicy.description.ilike(pattern),
                    RateLimitPolicy.route_pattern.ilike(pattern),
                )
            )

        if is_enabled is not None:
            statement = statement.where(
                RateLimitPolicy.is_enabled.is_(is_enabled),
            )

        if scope is not None:
            statement = statement.where(
                RateLimitPolicy.scope == scope,
            )

        statement = (
            statement
            .order_by(
                RateLimitPolicy.priority.asc(),
                RateLimitPolicy.id.asc(),
            )
            .offset(skip)
            .limit(limit)
        )

        return list(db.execute(statement).scalars().all())

    def count_filtered(
        self,
        db: Session,
        *,
        search: str | None = None,
        is_enabled: bool | None = None,
        scope: str | None = None,
    ) -> int:
        statement = select(
            func.count(RateLimitPolicy.id)
        )

        if search:
            pattern = f"%{search.strip()}%"

            statement = statement.where(
                or_(
                    RateLimitPolicy.key.ilike(pattern),
                    RateLimitPolicy.name.ilike(pattern),
                    RateLimitPolicy.description.ilike(pattern),
                    RateLimitPolicy.route_pattern.ilike(pattern),
                )
            )

        if is_enabled is not None:
            statement = statement.where(
                RateLimitPolicy.is_enabled.is_(is_enabled),
            )

        if scope is not None:
            statement = statement.where(
                RateLimitPolicy.scope == scope,
            )

        return int(db.execute(statement).scalar_one())


rate_limit_policy_repository = RateLimitPolicyRepository()