from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.services.api_key_service import api_key_service


def api_key_guard(required_scope: str | None = None):
    def dependency(
        request: Request,
        x_api_key: str | None = Header(default=None, alias="X-API-Key"),
        db: Session = Depends(get_db),
    ):
        if not x_api_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing API key.",
            )

        result = api_key_service.validate_api_key(
            db=db,
            plain_key=x_api_key,
            required_scope=required_scope,
            ip_address=request.client.host if request.client else None,
        )

        if not result.valid:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid or unauthorized API key.",
            )

        return result

    return dependency