from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

import httpx

from app.common.exceptions import AppException
from app.schemas.oauth import OAuthProviderName, OAuthProviderProfile
from app.services.oauth.base import OAuthProvider, OAuthTokenSet


class GoogleOAuthProvider(OAuthProvider):
    """Google OpenID Connect implementation.

    Configuration is injected at runtime from the existing integrations table;
    no credentials are read from hardcoded constants or exposed to clients.
    """

    name = OAuthProviderName.GOOGLE

    AUTHORIZATION_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"

    def __init__(
        self,
        *,
        client_id: str | None,
        client_secret: str | None,
        timeout_seconds: float = 20.0,
    ) -> None:
        self.client_id = (client_id or "").strip()
        self.client_secret = (client_secret or "").strip()
        self.timeout_seconds = timeout_seconds

    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def _require_configuration(self) -> None:
        if not self.is_configured():
            raise AppException(
                message="Google OAuth is not configured.",
                status_code=503,
                error_code="OAUTH_PROVIDER_NOT_CONFIGURED",
            )

    def build_authorization_url(
        self,
        *,
        state: str,
        redirect_uri: str,
        code_challenge: str | None = None,
        code_challenge_method: str | None = None,
    ) -> str:
        self._require_configuration()

        params: dict[str, str] = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "access_type": "offline",
            "include_granted_scopes": "true",
            "prompt": "select_account",
        }

        if code_challenge:
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = code_challenge_method or "S256"

        return f"{self.AUTHORIZATION_URL}?{urlencode(params)}"

    async def exchange_code(
        self,
        *,
        code: str,
        redirect_uri: str,
        code_verifier: str | None = None,
    ) -> OAuthTokenSet:
        self._require_configuration()

        payload: dict[str, str] = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        }
        if code_verifier:
            payload["code_verifier"] = code_verifier

        data = await self._request_json(
            method="POST",
            url=self.TOKEN_URL,
            data=payload,
            error_code="OAUTH_CODE_EXCHANGE_FAILED",
        )

        access_token = str(data.get("access_token") or "").strip()
        if not access_token:
            raise AppException(
                message="Google did not return an access token.",
                status_code=502,
                error_code="OAUTH_INVALID_TOKEN_RESPONSE",
            )

        expires_in_value = data.get("expires_in")
        expires_in = int(expires_in_value) if expires_in_value is not None else None

        return OAuthTokenSet(
            access_token=access_token,
            token_type=str(data.get("token_type") or "Bearer"),
            expires_in=expires_in,
            refresh_token=(str(data["refresh_token"]) if data.get("refresh_token") else None),
            id_token=(str(data["id_token"]) if data.get("id_token") else None),
            scope=(str(data["scope"]) if data.get("scope") else None),
            raw=data,
        )

    async def fetch_profile(
        self,
        *,
        token_set: OAuthTokenSet,
    ) -> OAuthProviderProfile:
        data = await self._request_json(
            method="GET",
            url=self.USERINFO_URL,
            headers={"Authorization": f"Bearer {token_set.access_token}"},
            error_code="OAUTH_PROFILE_FETCH_FAILED",
        )

        provider_user_id = str(data.get("sub") or "").strip()
        if not provider_user_id:
            raise AppException(
                message="Google profile does not contain a subject identifier.",
                status_code=502,
                error_code="OAUTH_INVALID_PROFILE",
            )

        email = str(data.get("email") or "").strip().lower() or None
        full_name = str(data.get("name") or "").strip() or None
        avatar_url = str(data.get("picture") or "").strip() or None

        return OAuthProviderProfile(
            provider=self.name,
            provider_user_id=provider_user_id,
            email=email,
            email_verified=bool(data.get("email_verified", False)),
            full_name=full_name,
            username=None,
            avatar_url=avatar_url,
        )

    async def _request_json(
        self,
        *,
        method: str,
        url: str,
        error_code: str,
        data: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.request(
                    method,
                    url,
                    data=data,
                    headers=headers,
                )
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise AppException(
                message="Google OAuth request failed.",
                status_code=502,
                error_code=error_code,
            ) from exc

        if not isinstance(payload, dict):
            raise AppException(
                message="Google OAuth returned an invalid response.",
                status_code=502,
                error_code=error_code,
            )
        return payload
