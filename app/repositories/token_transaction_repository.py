from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.enums import TokenTransactionType
from app.models.token_transaction import TokenTransaction
from app.repositories.base import BaseRepository


class TokenTransactionRepository(BaseRepository[TokenTransaction]):
    def __init__(self):
        super().__init__(TokenTransaction)

    def list_by_user_id(
        self,
        db: Session,
        user_id: int,
        *,
        skip: int = 0,
        limit: int = 50,
    ) -> list[TokenTransaction]:
        statement = (
            select(TokenTransaction)
            .where(TokenTransaction.user_id == user_id)
            .order_by(TokenTransaction.created_at.desc())
            .offset(skip)
            .limit(limit)
        )

        return list(db.execute(statement).scalars().all())

    def sum_credits(self, db: Session) -> int:
        statement = (
            select(func.coalesce(func.sum(TokenTransaction.amount), 0))
            .where(TokenTransaction.transaction_type == TokenTransactionType.CREDIT.value)
        )
        return int(db.execute(statement).scalar_one())

    def sum_debits(self, db: Session) -> int:
        statement = (
            select(func.coalesce(func.sum(TokenTransaction.amount), 0))
            .where(TokenTransaction.transaction_type == TokenTransactionType.DEBIT.value)
        )
        return abs(int(db.execute(statement).scalar_one()))


token_transaction_repository = TokenTransactionRepository()