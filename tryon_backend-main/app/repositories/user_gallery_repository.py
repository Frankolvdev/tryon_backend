from sqlalchemy import (
    func,
    or_,
    select,
)
from sqlalchemy.orm import Session

from app.models.user_gallery_item import (
    UserGalleryItem,
)


class UserGalleryRepository:
    def get_by_id(
        self,
        db: Session,
        *,
        gallery_item_id: int,
    ) -> UserGalleryItem | None:
        return db.get(
            UserGalleryItem,
            gallery_item_id,
        )

    def get_for_user(
        self,
        db: Session,
        *,
        gallery_item_id: int,
        user_id: int,
        include_deleted: bool = False,
    ) -> UserGalleryItem | None:
        statement = select(
            UserGalleryItem
        ).where(
            UserGalleryItem.id
            == gallery_item_id,
            UserGalleryItem.user_id
            == user_id,
        )

        if not include_deleted:
            statement = statement.where(
                UserGalleryItem.is_deleted.is_(
                    False
                )
            )

        return db.execute(
            statement
        ).scalar_one_or_none()

    def get_by_tryon_job(
        self,
        db: Session,
        *,
        user_id: int,
        tryon_job_id: int,
    ) -> UserGalleryItem | None:
        statement = select(
            UserGalleryItem
        ).where(
            UserGalleryItem.user_id
            == user_id,
            UserGalleryItem.tryon_job_id
            == tryon_job_id,
            UserGalleryItem.is_deleted.is_(
                False
            ),
        )

        return db.execute(
            statement
        ).scalar_one_or_none()

    def list_for_user(
        self,
        db: Session,
        *,
        user_id: int,
        favorite: bool | None = None,
        archived: bool | None = False,
        category: str | None = None,
        search: str | None = None,
        include_deleted: bool = False,
        skip: int = 0,
        limit: int = 50,
    ) -> list[UserGalleryItem]:
        statement = select(
            UserGalleryItem
        ).where(
            UserGalleryItem.user_id
            == user_id
        )

        if not include_deleted:
            statement = statement.where(
                UserGalleryItem.is_deleted.is_(
                    False
                )
            )

        if favorite is not None:
            statement = statement.where(
                UserGalleryItem.is_favorite.is_(
                    favorite
                )
            )

        if archived is not None:
            statement = statement.where(
                UserGalleryItem.is_archived.is_(
                    archived
                )
            )

        if category:
            statement = statement.where(
                UserGalleryItem.category
                == category
            )

        if search:
            pattern = f"%{search.strip()}%"

            statement = statement.where(
                or_(
                    UserGalleryItem.title.ilike(
                        pattern
                    ),
                    UserGalleryItem.description.ilike(
                        pattern
                    ),
                )
            )

        statement = (
            statement
            .order_by(
                UserGalleryItem.created_at.desc()
            )
            .offset(skip)
            .limit(limit)
        )

        return list(
            db.execute(
                statement
            ).scalars().all()
        )

    def count_for_user(
        self,
        db: Session,
        *,
        user_id: int,
        favorite: bool | None = None,
        archived: bool | None = False,
        category: str | None = None,
        search: str | None = None,
        include_deleted: bool = False,
    ) -> int:
        statement = select(
            func.count(
                UserGalleryItem.id
            )
        ).where(
            UserGalleryItem.user_id
            == user_id
        )

        if not include_deleted:
            statement = statement.where(
                UserGalleryItem.is_deleted.is_(
                    False
                )
            )

        if favorite is not None:
            statement = statement.where(
                UserGalleryItem.is_favorite.is_(
                    favorite
                )
            )

        if archived is not None:
            statement = statement.where(
                UserGalleryItem.is_archived.is_(
                    archived
                )
            )

        if category:
            statement = statement.where(
                UserGalleryItem.category
                == category
            )

        if search:
            pattern = f"%{search.strip()}%"

            statement = statement.where(
                or_(
                    UserGalleryItem.title.ilike(
                        pattern
                    ),
                    UserGalleryItem.description.ilike(
                        pattern
                    ),
                )
            )

        return int(
            db.execute(
                statement
            ).scalar_one()
        )


user_gallery_repository = (
    UserGalleryRepository()
)