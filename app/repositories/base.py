from typing import Any, Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import Base


ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    def __init__(self, model: type[ModelType]):
        self.model = model

    def get_by_id(self, db: Session, id: int) -> ModelType | None:
        statement = select(self.model).where(self.model.id == id)
        return db.execute(statement).scalar_one_or_none()

    def get_all(
        self,
        db: Session,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> list[ModelType]:
        statement = select(self.model).offset(skip).limit(limit)
        return list(db.execute(statement).scalars().all())

    def create(self, db: Session, *, data: dict[str, Any]) -> ModelType:
        db_obj = self.model(**data)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update(
        self,
        db: Session,
        *,
        db_obj: ModelType,
        data: dict[str, Any],
    ) -> ModelType:
        for field, value in data.items():
            setattr(db_obj, field, value)

        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def delete(self, db: Session, *, db_obj: ModelType) -> None:
        db.delete(db_obj)
        db.commit()