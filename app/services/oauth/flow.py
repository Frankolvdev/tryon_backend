from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlparse

import jwt
from redis.exceptions import RedisError
from sqlalchemy.orm import Session

from app.common.enums import UserRole, UserStatus
from app.common.exceptions import AppException, ForbiddenException, UnauthorizedException
from app.common.time import utc_now
from app.core.config import settings
from app.core.redis_client import redis_client
from app.models.oauth_account import OAuthAccount
from app.models.user import User
from app.repositories.oauth_account_repository import oauth_account_repository
from app.repositories.user_repository import user_repository
from app.schemas.oauth import OAuthProviderName, OAuthProviderProfile
from app.services.account_security_service import account_security_service
from app.services.auth_service import auth_service
from app.services.oauth.factory import build_oauth_provider_registry
from app.services.runtime_settings_service import runtime_settings_service
from app.services.token_service import token_service


class OAuthFlowService:
    STATE_TTL_SECONDS = 600
    GRANT_TTL_SECONDS = 120
    GRANT_PREFIX = "oauth:grant:"

    def _validate_frontend_redirect(self, redirect_uri: str) -> str:
        candidate = redirect_uri.strip()
        allowed = str(settings.FRONTEND_URL).rstrip("/")
        parsed_candidate = urlparse(candidate)
        parsed_allowed = urlparse(allowed)
        if (
            parsed_candidate.scheme not in {"http", "https"}
            or parsed_candidate.scheme != parsed_allowed.scheme
            or parsed_candidate.netloc != parsed_allowed.netloc
        ):
            raise AppException(
                message="OAuth redirect URI is not allowed.",
                status_code=400,
                error_code="OAUTH_REDIRECT_NOT_ALLOWED",
            )
        return candidate

    def create_state(
        self,
        *,
        provider: OAuthProviderName,
        frontend_redirect_uri: str,
        terms_accepted: bool,
        terms_version: str | None,
        age_confirmed: bool,
    ) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            "type": "oauth_state",
            "provider": provider.value,
            "redirect_uri": self._validate_frontend_redirect(frontend_redirect_uri),
            "terms_accepted": terms_accepted,
            "terms_version": terms_version,
            "age_confirmed": age_confirmed,
            "nonce": secrets.token_urlsafe(24),
            "iat": now,
            "exp": now + timedelta(seconds=self.STATE_TTL_SECONDS),
        }
        return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

    def decode_state(self, state: str, provider: OAuthProviderName) -> dict:
        try:
            payload = jwt.decode(
                state,
                settings.SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM],
            )
        except jwt.PyJWTError as exc:
            raise UnauthorizedException("Invalid or expired OAuth state.") from exc
        if payload.get("type") != "oauth_state" or payload.get("provider") != provider.value:
            raise UnauthorizedException("Invalid OAuth state.")
        payload["redirect_uri"] = self._validate_frontend_redirect(str(payload.get("redirect_uri") or ""))
        return payload

    def authorization_url(
        self,
        db: Session,
        *,
        provider_name: OAuthProviderName,
        backend_callback_uri: str,
        frontend_redirect_uri: str,
        terms_accepted: bool,
        terms_version: str | None,
        age_confirmed: bool,
    ) -> tuple[str, str]:
        registry = build_oauth_provider_registry(db)
        try:
            provider = registry.get(provider_name)
        except LookupError as exc:
            raise AppException(
                message="OAuth provider is not available.",
                status_code=404,
                error_code="OAUTH_PROVIDER_NOT_AVAILABLE",
            ) from exc
        state = self.create_state(
            provider=provider_name,
            frontend_redirect_uri=frontend_redirect_uri,
            terms_accepted=terms_accepted,
            terms_version=terms_version,
            age_confirmed=age_confirmed,
        )
        return provider.build_authorization_url(
            state=state,
            redirect_uri=backend_callback_uri,
        ), state

    def _is_admin(self, user: User) -> bool:
        return bool(user.is_superuser or user.role in {"admin", "superadmin", "super_admin"})

    def _resolve_user(
        self,
        db: Session,
        *,
        profile: OAuthProviderProfile,
        state_payload: dict,
    ) -> User:
        provider_value = profile.provider.value
        identity = oauth_account_repository.get_by_provider_identity(
            db,
            provider=provider_value,
            provider_user_id=profile.provider_user_id,
        )
        if identity is not None:
            user = user_repository.get_by_id(db, identity.user_id)
            if user is None or not identity.is_active:
                raise UnauthorizedException("OAuth account is not available.")
            identity.last_login_at = utc_now()
            db.add(identity)
            db.commit()
            return user

        if profile.email is None or not profile.email_verified:
            raise ForbiddenException("The OAuth provider must return a verified email address.")

        email = str(profile.email).strip().lower()
        user = user_repository.get_by_email(db, email)
        if user is not None:
            if self._is_admin(user):
                raise ForbiddenException("Administrative accounts cannot be linked through public OAuth login.")
        else:
            security_settings = account_security_service.get_or_create_settings(db)
            if not runtime_settings_service.registration_enabled(db) or not security_settings.registration_enabled:
                raise ForbiddenException("Registration is currently disabled.")
            if security_settings.require_terms_acceptance and not bool(state_payload.get("terms_accepted")):
                raise ForbiddenException("You must accept the terms and conditions.")
            if security_settings.require_age_confirmation and not bool(state_payload.get("age_confirmed")):
                raise ForbiddenException("You must confirm that you meet the minimum age requirement.")

            user = user_repository.create(
                db,
                data={
                    "email": email,
                    "hashed_password": None,
                    "full_name": profile.full_name,
                    "auth_provider": provider_value,
                    "provider_user_id": profile.provider_user_id,
                    "role": UserRole.USER.value,
                    "status": UserStatus.ACTIVE.value,
                    "is_active": True,
                    "is_verified": True,
                },
            )
            security = account_security_service.get_or_create_user_security(db, user_id=user.id)
            security.account_status = "active"
            security.email_verified = True
            security.email_verified_at = utc_now()
            security.verification_required = False
            security.terms_accepted = bool(state_payload.get("terms_accepted"))
            security.terms_version = state_payload.get("terms_version")
            security.terms_accepted_at = utc_now() if security.terms_accepted else None
            security.age_confirmed = bool(state_payload.get("age_confirmed"))
            security.age_confirmed_at = utc_now() if security.age_confirmed else None
            db.add(security)
            db.commit()
            free_tokens = runtime_settings_service.free_signup_tokens(db)
            if free_tokens > 0:
                token_service.credit_tokens(
                    db=db,
                    user_id=user.id,
                    amount=free_tokens,
                    source="signup_bonus",
                    description="Free signup tokens.",
                )
                db.refresh(user)

        existing_for_user = oauth_account_repository.get_by_user_provider(
            db,
            user_id=user.id,
            provider=provider_value,
        )
        if existing_for_user is not None and existing_for_user.provider_user_id != profile.provider_user_id:
            raise ForbiddenException("This user already has a different account linked for this provider.")

        if existing_for_user is None:
            db.add(
                OAuthAccount(
                    user_id=user.id,
                    provider=provider_value,
                    provider_user_id=profile.provider_user_id,
                    provider_email=email,
                    provider_username=profile.username,
                    provider_avatar_url=str(profile.avatar_url) if profile.avatar_url else None,
                    email_verified=profile.email_verified,
                    is_active=True,
                    last_login_at=utc_now(),
                )
            )
            db.commit()
        return user

    async def callback(
        self,
        db: Session,
        *,
        provider_name: OAuthProviderName,
        code: str,
        state: str,
        backend_callback_uri: str,
    ) -> tuple[str, str]:
        state_payload = self.decode_state(state, provider_name)
        registry = build_oauth_provider_registry(db)
        try:
            provider = registry.get(provider_name)
        except LookupError as exc:
            raise AppException("OAuth provider is not available.", 404, "OAUTH_PROVIDER_NOT_AVAILABLE") from exc
        token_set = await provider.exchange_code(code=code, redirect_uri=backend_callback_uri)
        profile = await provider.fetch_profile(token_set=token_set)
        user = self._resolve_user(db, profile=profile, state_payload=state_payload)
        auth_service._validate_account_access(db, user=user)
        grant = secrets.token_urlsafe(48)
        try:
            redis_client.get_client().setex(
                f"{self.GRANT_PREFIX}{grant}",
                self.GRANT_TTL_SECONDS,
                json.dumps({"user_id": user.id}),
            )
        except RedisError as exc:
            raise AppException(
                message="OAuth session service is temporarily unavailable.",
                status_code=503,
                error_code="OAUTH_SESSION_UNAVAILABLE",
            ) from exc
        return str(state_payload["redirect_uri"]), grant

    def exchange_grant(
        self,
        db: Session,
        *,
        grant: str,
        user_agent: str | None,
        ip_address: str | None,
    ) -> dict:
        key = f"{self.GRANT_PREFIX}{grant}"
        try:
            raw = redis_client.get_client().getdel(key)
        except RedisError as exc:
            raise AppException("OAuth session service is temporarily unavailable.", 503, "OAUTH_SESSION_UNAVAILABLE") from exc
        if not raw:
            raise UnauthorizedException("Invalid or expired OAuth authorization code.")
        try:
            user_id = int(json.loads(raw)["user_id"])
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            raise UnauthorizedException("Invalid OAuth authorization code.") from exc
        user = user_repository.get_by_id(db, user_id)
        if user is None:
            raise UnauthorizedException("Invalid user.")
        auth_service._validate_account_access(db, user=user)
        return auth_service.issue_session_tokens(
            db,
            user=user,
            user_agent=user_agent,
            ip_address=ip_address,
            mfa_setup_required=False,
        )

    @staticmethod
    def callback_redirect(frontend_redirect_uri: str, grant: str) -> str:
        separator = "&" if "?" in frontend_redirect_uri else "?"
        return f"{frontend_redirect_uri}{separator}{urlencode({'code': grant})}"


oauth_flow_service = OAuthFlowService()
