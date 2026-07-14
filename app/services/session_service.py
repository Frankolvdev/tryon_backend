from __future__ import annotations

from sqlalchemy.orm import Session

from app.common.exceptions import (
    NotFoundException,
)
from app.common.time import utc_now
from app.models.refresh_token import (
    RefreshToken,
)
from app.models.user import User
from app.repositories.refresh_token_repository import (
    refresh_token_repository,
)
from app.schemas.session import (
    SessionListResponse,
    SessionResponse,
    SessionRevokeResponse,
    SessionsRevokeResponse,
)


class SessionService:
    def _parse_user_agent(
        self,
        user_agent: str | None,
    ) -> tuple[
        str | None,
        str | None,
        str | None,
    ]:
        if not user_agent:
            return (
                None,
                None,
                None,
            )

        normalized = user_agent.lower()

        browser_name = "Unknown browser"

        if "edg/" in normalized:
            browser_name = "Microsoft Edge"

        elif "opr/" in normalized:
            browser_name = "Opera"

        elif "chrome/" in normalized:
            browser_name = "Google Chrome"

        elif "firefox/" in normalized:
            browser_name = "Mozilla Firefox"

        elif (
            "safari/" in normalized
            and "chrome/" not in normalized
        ):
            browser_name = "Safari"

        operating_system = "Unknown OS"

        if "windows" in normalized:
            operating_system = "Windows"

        elif "android" in normalized:
            operating_system = "Android"

        elif (
            "iphone" in normalized
            or "ipad" in normalized
        ):
            operating_system = "iOS"

        elif "mac os" in normalized:
            operating_system = "macOS"

        elif "linux" in normalized:
            operating_system = "Linux"

        device_name = (
            f"{browser_name} on "
            f"{operating_system}"
        )

        return (
            device_name,
            browser_name,
            operating_system,
        )

    def _response(
        self,
        session: RefreshToken,
        *,
        current_session_id: int | None,
    ) -> SessionResponse:
        (
            device_name,
            browser_name,
            operating_system,
        ) = self._parse_user_agent(
            session.user_agent
        )

        now = utc_now()

        is_expired = (
            session.expires_at <= now
        )

        return SessionResponse(
            id=session.id,
            user_agent=session.user_agent,
            ip_address=session.ip_address,
            is_revoked=session.is_revoked,
            expires_at=session.expires_at,
            created_at=session.created_at,
            revoked_at=session.revoked_at,
            is_expired=is_expired,
            is_current=(
                current_session_id is not None
                and session.id
                == current_session_id
            ),
            device_name=device_name,
            browser_name=browser_name,
            operating_system=(
                operating_system
            ),
        )

    def list_user_sessions(
        self,
        db: Session,
        *,
        user: User,
        current_session_id: int | None = None,
    ) -> SessionListResponse:
        sessions = (
            refresh_token_repository
            .get_all_by_user_id(
                db=db,
                user_id=user.id,
            )
        )

        items = [
            self._response(
                session,
                current_session_id=(
                    current_session_id
                ),
            )
            for session in sessions
        ]

        active = sum(
            1
            for item in items
            if (
                not item.is_revoked
                and not item.is_expired
            )
        )

        revoked = sum(
            1
            for item in items
            if item.is_revoked
        )

        expired = sum(
            1
            for item in items
            if item.is_expired
        )

        return SessionListResponse(
            items=items,
            total=len(items),
            active=active,
            revoked=revoked,
            expired=expired,
        )

    def revoke_session(
        self,
        db: Session,
        *,
        user_id: int,
        session_id: int,
    ) -> SessionRevokeResponse:
        session = (
            refresh_token_repository
            .get_by_id(
                db,
                session_id,
            )
        )

        if (
            session is None
            or session.user_id != user_id
        ):
            raise NotFoundException(
                "Session not found."
            )

        if not session.is_revoked:
            session.is_revoked = True
            session.revoked_at = utc_now()

            db.add(session)
            db.commit()

        return SessionRevokeResponse(
            success=True,
            session_id=session.id,
            message=(
                "Session closed successfully."
            ),
        )

    def revoke_other_sessions(
        self,
        db: Session,
        *,
        user_id: int,
        current_session_id: int,
    ) -> SessionsRevokeResponse:
        current_session = (
            refresh_token_repository
            .get_by_id(
                db,
                current_session_id,
            )
        )

        if (
            current_session is None
            or current_session.user_id
            != user_id
        ):
            raise NotFoundException(
                "Current session not found."
            )

        sessions = (
            refresh_token_repository
            .get_active_by_user_id(
                db=db,
                user_id=user_id,
            )
        )

        revoked = 0
        now = utc_now()

        for session in sessions:
            if session.id == current_session_id:
                continue

            if session.is_revoked:
                continue

            session.is_revoked = True
            session.revoked_at = now

            db.add(session)
            revoked += 1

        if revoked > 0:
            db.commit()

        return SessionsRevokeResponse(
            success=True,
            revoked_sessions=revoked,
            message=(
                "All other sessions were closed."
            ),
        )

    def revoke_all_sessions(
        self,
        db: Session,
        *,
        user_id: int,
    ) -> SessionsRevokeResponse:
        sessions = (
            refresh_token_repository
            .get_active_by_user_id(
                db=db,
                user_id=user_id,
            )
        )

        revoked = 0
        now = utc_now()

        for session in sessions:
            if session.is_revoked:
                continue

            session.is_revoked = True
            session.revoked_at = now

            db.add(session)
            revoked += 1

        if revoked > 0:
            db.commit()

        return SessionsRevokeResponse(
            success=True,
            revoked_sessions=revoked,
            message=(
                "All active sessions were closed."
            ),
        )


session_service = SessionService()