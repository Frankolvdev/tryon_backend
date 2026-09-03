from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from app.schemas.oauth import OAuthProviderName, OAuthProviderProfile


@dataclass(frozen=True, slots=True)
class OAuthTokenSet:
    access_token: str
    token_type: str = "Bearer"
    expires_in: int | None = None
    refresh_token: str | None = None
    id_token: str | None = None
    scope: str | None = None
    raw: dict[str, Any] | None = None


class OAuthProvider(ABC):
    """Provider contract shared by Google, GitHub, Facebook and Apple."""

    name: OAuthProviderName

    @abstractmethod
    def is_configured(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def build_authorization_url(
        self,
        *,
        state: str,
        redirect_uri: str,
        code_challenge: str | None = None,
        code_challenge_method: str | None = None,
    ) -> str:
        raise NotImplementedError

    @abstractmethod
    async def exchange_code(
        self,
        *,
        code: str,
        redirect_uri: str,
        code_verifier: str | None = None,
    ) -> OAuthTokenSet:
        raise NotImplementedError

    @abstractmethod
    async def fetch_profile(
        self,
        *,
        token_set: OAuthTokenSet,
    ) -> OAuthProviderProfile:
        raise NotImplementedError
