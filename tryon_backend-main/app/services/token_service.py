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
from app.schemas.token import TokenPackageCreate, TokenPackageResponse, TokenPackageUpdate
from app.services.pricing_service import pricing_service


class TokenService:
    def _package_response(self, db: Session, package: TokenPackage) -> TokenPackageResponse:
        calculated_price, currency = pricing_service.price_for_tokens(
            db, package.tokens_amount
        )
        calculated_cents = int(round(calculated_price * 100))
        return TokenPackageResponse(
            id=package.id,
            name=package.name,
            description=package.description,
            tokens_amount=package.tokens_amount,
            price_cents=package.price_cents,
            calculated_price_cents=calculated_cents,
            commercial_token_value=pricing_service._token_value(db),
            price_is_automatic=True,
            currency=currency.lower(),
            stripe_price_id=package.stripe_price_id,
            is_active=package.is_active,
            created_at=package.created_at,
        )

    def get_balance(self, user: User) -> int:
        return user.token_balance

    def list_public_packages(self, db: Session) -> list[TokenPackageResponse]:
        return [
            self._package_response(db, item)
            for item in token_package_repository.list_active(db)
        ]

    def list_admin_packages(self, db: Session) -> list[TokenPackageResponse]:
        return [
            self._package_response(db, item)
            for item in token_package_repository.list_all(db)
        ]

    def create_package(
        self,
        db: Session,
        data: TokenPackageCreate,
    ) -> TokenPackageResponse:
        calculated_price, currency = pricing_service.price_for_tokens(
            db, data.tokens_amount
        )
        package = token_package_repository.create(
            db,
            data={
                **data.model_dump(exclude={"price_cents", "currency"}),
                "price_cents": int(round(calculated_price * 100)),
                "currency": currency.lower(),
            },
        )
        return self._package_response(db, package)

    def update_package(
        self,
        db: Session,
        package_id: int,
        data: TokenPackageUpdate,
    ) -> TokenPackageResponse:
        package_obj = token_package_repository.get_by_id(db, package_id)

        if not package_obj:
            raise NotFoundException("Token package not found.")

        update_data = data.model_dump(
            exclude_unset=True,
            exclude={"price_cents", "currency"},
        )
        final_tokens = int(update_data.get("tokens_amount", package_obj.tokens_amount))
        calculated_price, currency = pricing_service.price_for_tokens(
            db, final_tokens
        )
        update_data["price_cents"] = int(round(calculated_price * 100))
        update_data["currency"] = currency.lower()
        package = token_package_repository.update(
            db,
            db_obj=package_obj,
            data=update_data,
        )
        return self._package_response(db, package)

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

    def get_admin_transactions(
        self,
        db: Session,
        *,
        user_id: int | None = None,
        transaction_type: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[TokenTransaction]:
        return token_transaction_repository.list_all_filtered(
            db, user_id=user_id, transaction_type=transaction_type, skip=skip, limit=limit
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