from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.token_package import TokenPackage
from app.repositories.base import BaseRepository


class TokenPackageRepository(BaseRepository[TokenPackage]):
    def __init__(self):
        super().__init__(TokenPackage)

    def list_active(self, db: Session) -> list[TokenPackage]:
        statement = (
            select(TokenPackage)
            .where(TokenPackage.is_active.is_(True))
            .order_by(TokenPackage.price_cents.asc())
        )

        return list(db.execute(statement).scalars().all())

    def list_all(self, db: Session) -> list[TokenPackage]:
        statement = select(TokenPackage).order_by(TokenPackage.id.asc())
        return list(db.execute(statement).scalars().all())


token_package_repository = TokenPackageRepository()