from typing import Any

from sqlalchemy.orm import Session

from app.common.cache_enums import CacheNamespace
from app.models.user import User
from app.repositories.user_repository import (
    user_repository,
)
from app.services.cache_stampede_service import (
    cache_stampede_service,
)
from app.services.distributed_cache_service import (
    distributed_cache_service,
)


class UserCacheService:
    USER_TTL_SECONDS = 300
    USER_BY_EMAIL_TTL_SECONDS = 300

    def _serialize_user(
        self,
        user: User,
    ) -> dict[str, Any]:
        data: dict[str, Any] = {}

        for column in user.__table__.columns:
            value = getattr(
                user,
                column.name,
            )

            if column.name in {
                "hashed_password",
                "password_hash",
            }:
                continue

            data[column.name] = value

        return data

    def get_by_id(
        self,
        db: Session,
        *,
        user_id: int,
    ) -> dict[str, Any] | None:
        return cache_stampede_service.remember_optional(
            namespace=CacheNamespace.USERS,
            parts=["id", user_id],
            loader=lambda: (
                self._serialize_user(user)
                if (
                    user := user_repository.get_by_id(
                        db,
                        user_id,
                    )
                )
                else None
            ),
            ttl_seconds=self.USER_TTL_SECONDS,
            negative_ttl_seconds=30,
            tags=[
                f"user:{user_id}",
                "users",
            ],
        )

    def get_by_email(
        self,
        db: Session,
        *,
        email: str,
    ) -> dict[str, Any] | None:
        normalized_email = (
            email.strip().lower()
        )

        return cache_stampede_service.remember_optional(
            namespace=CacheNamespace.USERS,
            parts=["email", normalized_email],
            loader=lambda: (
                self._serialize_user(user)
                if (
                    user := user_repository.get_by_email(
                        db,
                        normalized_email,
                    )
                )
                else None
            ),
            ttl_seconds=(
                self.USER_BY_EMAIL_TTL_SECONDS
            ),
            negative_ttl_seconds=30,
            tags=[
                f"user-email:{normalized_email}",
                "users",
            ],
        )

    def invalidate(
        self,
        *,
        user_id: int,
        email: str | None = None,
    ) -> None:
        distributed_cache_service.invalidate_tag(
            tag=f"user:{user_id}"
        )

        if email:
            distributed_cache_service.invalidate_tag(
                tag=(
                    f"user-email:"
                    f"{email.strip().lower()}"
                )
            )


user_cache_service = UserCacheService()