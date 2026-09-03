from fastapi import Depends, HTTPException, status

from app.api.v1.guards.auth_guard import auth_guard
from app.common.enums import UserRole


def superadmin_guard(
    current_user=Depends(auth_guard),
):
    if current_user.role != UserRole.SUPERADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superadmin access required.",
        )

    return current_user