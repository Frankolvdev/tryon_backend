from fastapi import Depends

from app.api.v1.guards.auth_guard import auth_guard
from app.common.enums import UserRole
from app.common.exceptions import AppException
from app.models.user import User


def commercial_account_guard(current_user: User = Depends(auth_guard)) -> User:
    if current_user.role == UserRole.OWNER.value:
        raise AppException(
            "Owner accounts do not use plans, token purchases or commercial billing.",
            status_code=403,
            error_code="OWNER_COMMERCIAL_BILLING_DISABLED",
        )
    return current_user
