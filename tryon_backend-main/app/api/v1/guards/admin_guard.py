from fastapi import Depends, HTTPException, status

from app.api.v1.guards.auth_guard import auth_guard
from app.common.enums import UserRole


def admin_guard(
    current_user=Depends(auth_guard),
):
    if current_user.role not in [
        UserRole.ADMIN.value,
        UserRole.SUPERADMIN.value,
    ]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required.",
        )

    return current_user