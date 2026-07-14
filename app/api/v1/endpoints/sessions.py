from fastapi import (
    APIRouter,
    Depends,
    Header,
    Request,
)
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.auth_guard import (
    auth_guard,
)
from app.models.user import User
from app.schemas.session import (
    RevokeOtherSessionsRequest,
    SessionListResponse,
    SessionRevokeResponse,
    SessionsRevokeResponse,
)
from app.services.activity_service import (
    activity_service,
)
from app.services.session_service import (
    session_service,
)


router = APIRouter()


@router.get(
    "/",
    response_model=SessionListResponse,
)
def list_my_sessions(
    x_session_id: int | None = Header(
        default=None,
        alias="X-Session-ID",
    ),
    current_user: User = Depends(
        auth_guard
    ),
    db: Session = Depends(get_db),
):
    return session_service.list_user_sessions(
        db,
        user=current_user,
        current_session_id=x_session_id,
    )


@router.delete(
    "/{session_id}",
    response_model=SessionRevokeResponse,
)
def revoke_my_session(
    session_id: int,
    request: Request,
    current_user: User = Depends(
        auth_guard
    ),
    db: Session = Depends(get_db),
):
    result = session_service.revoke_session(
        db,
        user_id=current_user.id,
        session_id=session_id,
    )

    activity_service.create_log(
        db,
        user_id=current_user.id,
        action="session_revoked",
        description=(
            "User closed an active session."
        ),
        ip_address=(
            request.client.host
            if request.client
            else None
        ),
        user_agent=request.headers.get(
            "user-agent"
        ),
    )

    return result


@router.post(
    "/revoke-others",
    response_model=SessionsRevokeResponse,
)
def revoke_other_sessions(
    data: RevokeOtherSessionsRequest,
    request: Request,
    current_user: User = Depends(
        auth_guard
    ),
    db: Session = Depends(get_db),
):
    result = (
        session_service
        .revoke_other_sessions(
            db,
            user_id=current_user.id,
            current_session_id=(
                data.current_session_id
            ),
        )
    )

    activity_service.create_log(
        db,
        user_id=current_user.id,
        action="other_sessions_revoked",
        description=(
            "User closed all other sessions."
        ),
        ip_address=(
            request.client.host
            if request.client
            else None
        ),
        user_agent=request.headers.get(
            "user-agent"
        ),
    )

    return result


@router.post(
    "/revoke-all",
    response_model=SessionsRevokeResponse,
)
def revoke_all_sessions(
    request: Request,
    current_user: User = Depends(
        auth_guard
    ),
    db: Session = Depends(get_db),
):
    result = (
        session_service
        .revoke_all_sessions(
            db,
            user_id=current_user.id,
        )
    )

    activity_service.create_log(
        db,
        user_id=current_user.id,
        action="all_sessions_revoked",
        description=(
            "User closed all active sessions."
        ),
        ip_address=(
            request.client.host
            if request.client
            else None
        ),
        user_agent=request.headers.get(
            "user-agent"
        ),
    )

    return result