from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.user_profile_setting import (
    UserProfileSetting,
)


class UserProfileRepository:
    def get_by_user_id(
        self,
        db: Session,
        *,
        user_id: int,
    ) -> UserProfileSetting | None:
        statement = select(
            UserProfileSetting
        ).where(
            UserProfileSetting.user_id
            == user_id
        )

        return db.execute(
            statement
        ).scalar_one_or_none()

    def get_by_username(
        self,
        db: Session,
        *,
        username: str,
    ) -> UserProfileSetting | None:
        statement = select(
            UserProfileSetting
        ).where(
            func.lower(
                UserProfileSetting.username
            )
            == username.lower()
        )

        return db.execute(
            statement
        ).scalar_one_or_none()


user_profile_repository = (
    UserProfileRepository()
)