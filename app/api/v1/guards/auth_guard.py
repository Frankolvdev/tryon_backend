import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.db.database import SessionLocal
from app.core.jwt import decode_token
from app.services.user_service import user_service

security = HTTPBearer()


def auth_guard(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
):
    token = credentials.credentials

    try:
        payload = decode_token(token)
        user_id = int(payload.get("sub"))
        token_type = payload.get("type")
    except (jwt.PyJWTError, ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
        )

    if token_type != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type.",
        )

    user = user_service.get_user_by_id(db, user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user.",
        )

    return user

def auth_stream_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> int:
    """Authenticate a long-lived streaming request without retaining a DB session.

    FastAPI keeps yield-dependency cleanup until a StreamingResponse finishes. Using
    the regular auth_guard there would therefore keep get_db()/Session open for the
    whole SSE lifetime. This guard performs the same validation, but owns and closes
    its short-lived Session before the stream starts and returns only the user id.
    """
    token = credentials.credentials

    try:
        payload = decode_token(token)
        user_id = int(payload.get("sub"))
        token_type = payload.get("type")
    except (jwt.PyJWTError, ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
        )

    if token_type != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type.",
        )

    db = SessionLocal()
    try:
        user = user_service.get_user_by_id(db, user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found.",
            )
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Inactive user.",
            )
        return int(user.id)
    finally:
        db.close()

