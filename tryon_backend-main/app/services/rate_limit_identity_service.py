import hashlib
from typing import Any

from fastapi import Request
from jose import JWTError, jwt

from app.core.config import settings
from app.schemas.rate_limit_runtime import RateLimitIdentity


class RateLimitIdentityService:
    def _trusted_proxy_headers_enabled(self) -> bool:
        return bool(
            getattr(
                settings,
                "TRUST_PROXY_HEADERS",
                False,
            )
        )

    def get_client_ip(
        self,
        request: Request,
    ) -> str:
        if self._trusted_proxy_headers_enabled():
            forwarded_for = request.headers.get(
                "x-forwarded-for"
            )

            if forwarded_for:
                first_ip = forwarded_for.split(",")[0].strip()

                if first_ip:
                    return first_ip

            real_ip = request.headers.get("x-real-ip")

            if real_ip:
                return real_ip.strip()

            cloudflare_ip = request.headers.get(
                "cf-connecting-ip"
            )

            if cloudflare_ip:
                return cloudflare_ip.strip()

        if request.client and request.client.host:
            return request.client.host

        return "unknown"

    def _jwt_secret(self) -> str | None:
        possible_names = [
            "SECRET_KEY",
            "JWT_SECRET_KEY",
            "ACCESS_TOKEN_SECRET_KEY",
        ]

        for name in possible_names:
            value = getattr(settings, name, None)

            if value:
                return str(value)

        return None

    def _jwt_algorithm(self) -> str:
        possible_names = [
            "ALGORITHM",
            "JWT_ALGORITHM",
            "ACCESS_TOKEN_ALGORITHM",
        ]

        for name in possible_names:
            value = getattr(settings, name, None)

            if value:
                return str(value)

        return "HS256"

    def _extract_bearer_token(
        self,
        request: Request,
    ) -> str | None:
        authorization = request.headers.get(
            "authorization"
        )

        if not authorization:
            return None

        scheme, _, token = authorization.partition(" ")

        if scheme.lower() != "bearer":
            return None

        clean_token = token.strip()

        return clean_token or None

    def _decode_token(
        self,
        token: str,
    ) -> dict[str, Any] | None:
        secret = self._jwt_secret()

        if not secret:
            return None

        try:
            payload = jwt.decode(
                token,
                secret,
                algorithms=[self._jwt_algorithm()],
                options={
                    "verify_aud": False,
                },
            )

            return (
                payload
                if isinstance(payload, dict)
                else None
            )

        except JWTError:
            return None
        except Exception:
            return None

    def _extract_user_id(
        self,
        payload: dict[str, Any] | None,
    ) -> int | None:
        if not payload:
            return None

        possible_claims = [
            "user_id",
            "sub",
            "id",
        ]

        for claim in possible_claims:
            value = payload.get(claim)

            if value is None:
                continue

            try:
                return int(value)
            except (TypeError, ValueError):
                continue

        return None

    def _extract_api_key(
        self,
        request: Request,
    ) -> str | None:
        possible_headers = [
            "x-api-key",
            "api-key",
            "x-client-key",
        ]

        for header_name in possible_headers:
            value = request.headers.get(header_name)

            if value:
                return value.strip()

        authorization = request.headers.get(
            "authorization"
        )

        if authorization:
            scheme, _, token = authorization.partition(" ")

            if scheme.lower() in [
                "apikey",
                "api-key",
            ]:
                clean_token = token.strip()

                if clean_token:
                    return clean_token

        return None

    def _hash_api_key(
        self,
        api_key: str,
    ) -> str:
        return hashlib.sha256(
            api_key.encode("utf-8")
        ).hexdigest()

    def resolve(
        self,
        request: Request,
    ) -> RateLimitIdentity:
        ip_address = self.get_client_ip(request)

        bearer_token = self._extract_bearer_token(
            request
        )

        token_payload = (
            self._decode_token(bearer_token)
            if bearer_token
            else None
        )

        user_id = self._extract_user_id(
            token_payload
        )

        api_key = self._extract_api_key(request)

        api_key_hash = (
            self._hash_api_key(api_key)
            if api_key
            else None
        )

        return RateLimitIdentity(
            ip_address=ip_address,
            user_id=user_id,
            api_key_id=None,
            api_key_hash=api_key_hash,
            is_authenticated=user_id is not None,
        )


rate_limit_identity_service = RateLimitIdentityService()