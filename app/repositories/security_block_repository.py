from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.common.time import utc_now
from app.models.security_block import SecurityBlock
from app.repositories.base import BaseRepository


class SecurityBlockRepository(
    BaseRepository[SecurityBlock]
):
    def __init__(self):
        super().__init__(SecurityBlock)

    def find_active_block(
        self,
        db: Session,
        *,
        target_type: str,
        target_value: str,
    ) -> SecurityBlock | None:
        now = utc_now()

        statement = (
            select(SecurityBlock)
            .where(
                SecurityBlock.target_type == target_type,
                SecurityBlock.target_value == target_value,
                SecurityBlock.is_active.is_(True),
                SecurityBlock.starts_at <= now,
                or_(
                    SecurityBlock.is_permanent.is_(True),
                    SecurityBlock.expires_at.is_(None),
                    SecurityBlock.expires_at > now,
                ),
            )
            .order_by(
                SecurityBlock.created_at.desc(),
                SecurityBlock.id.desc(),
            )
            .limit(1)
        )

        return db.execute(
            statement
        ).scalar_one_or_none()

    def list_filtered(
        self,
        db: Session,
        *,
        target_type: str | None = None,
        is_active: bool | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[SecurityBlock]:
        statement = select(SecurityBlock)

        if target_type is not None:
            statement = statement.where(
                SecurityBlock.target_type
                == target_type
            )

        if is_active is not None:
            statement = statement.where(
                SecurityBlock.is_active.is_(
                    is_active
                )
            )

        statement = (
            statement
            .order_by(
                SecurityBlock.created_at.desc(),
                SecurityBlock.id.desc(),
            )
            .offset(skip)
            .limit(limit)
        )

        return list(
            db.execute(
                statement
            ).scalars().all()
        )

    def count_filtered(
        self,
        db: Session,
        *,
        target_type: str | None = None,
        is_active: bool | None = None,
    ) -> int:
        statement = select(
            func.count(SecurityBlock.id)
        )

        if target_type is not None:
            statement = statement.where(
                SecurityBlock.target_type
                == target_type
            )

        if is_active is not None:
            statement = statement.where(
                SecurityBlock.is_active.is_(
                    is_active
                )
            )

        return int(
            db.execute(
                statement
            ).scalar_one()
        )


security_block_repository = (
    SecurityBlockRepository()
)