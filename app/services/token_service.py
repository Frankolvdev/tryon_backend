from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.enums import TokenTransactionType
from app.common.exceptions import ConflictException, NotFoundException
from app.models.token_package import TokenPackage
from app.models.token_transaction import TokenTransaction
from app.models.user import User
from app.repositories.token_package_repository import token_package_repository
from app.repositories.token_transaction_repository import token_transaction_repository
from app.repositories.user_repository import user_repository
from app.schemas.token import TokenPackageCreate, TokenPackageUpdate


class TokenService:
    def get_balance(self, user: User) -> int:
        return user.token_balance

    def list_public_packages(self, db: Session) -> list[TokenPackage]:
        return token_package_repository.list_active(db)

    def list_admin_packages(self, db: Session) -> list[TokenPackage]:
        return token_package_repository.list_all(db)

    def create_package(
        self,
        db: Session,
        data: TokenPackageCreate,
    ) -> TokenPackage:
        return token_package_repository.create(
            db,
            data=data.model_dump(),
        )

    def update_package(
        self,
        db: Session,
        package_id: int,
        data: TokenPackageUpdate,
    ) -> TokenPackage:
        package_obj = token_package_repository.get_by_id(db, package_id)

        if not package_obj:
            raise NotFoundException("Token package not found.")

        return token_package_repository.update(
            db,
            db_obj=package_obj,
            data=data.model_dump(exclude_unset=True),
        )

    def get_user_transactions(
        self,
        db: Session,
        user_id: int,
        *,
        skip: int = 0,
        limit: int = 50,
    ) -> list[TokenTransaction]:
        return token_transaction_repository.list_by_user_id(
            db,
            user_id,
            skip=skip,
            limit=limit,
        )

    def credit_tokens(
        self,
        db: Session,
        *,
        user_id: int,
        amount: int,
        source: str,
        reference_id: str | None = None,
        description: str | None = None,
        commit: bool = True,
    ) -> User:
        if amount <= 0:
            raise ConflictException("Credit amount must be greater than zero.")

        user = db.execute(
            select(User)
            .where(User.id == user_id)
            .with_for_update()
        ).scalar_one_or_none()

        if not user:
            raise NotFoundException("User not found.")

        user.token_balance += amount

        transaction = TokenTransaction(
            user_id=user.id,
            transaction_type=TokenTransactionType.CREDIT.value,
            amount=amount,
            balance_after=user.token_balance,
            source=source,
            reference_id=reference_id,
            description=description,
        )

        db.add(user)
        db.add(transaction)
        if commit:
            db.commit()
            db.refresh(user)
        else:
            db.flush()

        return user

    def debit_tokens(
        self,
        db: Session,
        *,
        user_id: int,
        amount: int,
        source: str,
        reference_id: str | None = None,
        description: str | None = None,
        commit: bool = True,
    ) -> User:
        if amount <= 0:
            raise ConflictException("Debit amount must be greater than zero.")

        user = db.execute(
            select(User)
            .where(User.id == user_id)
            .with_for_update()
        ).scalar_one_or_none()

        if not user:
            raise NotFoundException("User not found.")

        if user.token_balance < amount:
            raise ConflictException("Insufficient token balance.")

        user.token_balance -= amount

        transaction = TokenTransaction(
            user_id=user.id,
            transaction_type=TokenTransactionType.DEBIT.value,
            amount=-amount,
            balance_after=user.token_balance,
            source=source,
            reference_id=reference_id,
            description=description,
        )

        db.add(user)
        db.add(transaction)
        if commit:
            db.commit()
            db.refresh(user)
        else:
            db.flush()

        return user

    def refund_tryon_tokens(
        self,
        db: Session,
        *,
        user_id: int,
        job_id: int,
        amount: int,
        reason: str | None = None,
    ) -> User:
        reference_id = str(job_id)
        user = db.execute(
            select(User)
            .where(User.id == user_id)
            .with_for_update()
        ).scalar_one_or_none()
        if not user:
            raise NotFoundException("User not found.")

        existing = token_transaction_repository.get_by_source_reference(
            db,
            user_id=user_id,
            source="tryon_refund",
            reference_id=reference_id,
        )
        if existing:
            db.rollback()
            return user

        return self.credit_tokens(
            db,
            user_id=user_id,
            amount=amount,
            source="tryon_refund",
            reference_id=reference_id,
            description=reason or "Automatic refund for failed try-on job",
        )

    def admin_adjust_tokens(
        self,
        db: Session,
        *,
        user_id: int,
        amount: int,
        description: str | None = None,
    ) -> User:
        user = user_repository.get_by_id(db, user_id)

        if not user:
            raise NotFoundException("User not found.")

        new_balance = user.token_balance + amount

        if new_balance < 0:
            raise ConflictException("Token balance cannot be negative.")

        transaction_type = (
            TokenTransactionType.CREDIT.value
            if amount >= 0
            else TokenTransactionType.DEBIT.value
        )

        user.token_balance = new_balance

        transaction = TokenTransaction(
            user_id=user.id,
            transaction_type=transaction_type,
            amount=amount,
            balance_after=user.token_balance,
            source="admin",
            description=description,
        )

        db.add(user)
        db.add(transaction)
        db.commit()
        db.refresh(user)

        return user


token_service = TokenService()