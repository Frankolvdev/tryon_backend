from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.auth_guard import auth_guard
from app.models.user import User
from app.services.rbac_service import rbac_service


def permission_guard(permission_key: str):
    def dependency(
        db: Session = Depends(get_db),
        current_user: User = Depends(auth_guard),
    ) -> User:
        if not rbac_service.user_has_permission(
            db,
            current_user,
            permission_key,
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )

        return current_user

    return dependency