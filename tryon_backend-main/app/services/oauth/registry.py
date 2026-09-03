from collections.abc import Iterable

from app.schemas.oauth import OAuthProviderName
from app.services.oauth.base import OAuthProvider


class OAuthProviderRegistry:
    """Explicit registry; providers are added by the application bootstrap."""

    def __init__(self, providers: Iterable[OAuthProvider] | None = None) -> None:
        self._providers: dict[OAuthProviderName, OAuthProvider] = {}
        for provider in providers or ():
            self.register(provider)

    def register(self, provider: OAuthProvider) -> None:
        if provider.name in self._providers:
            raise ValueError(
                f"OAuth provider '{provider.name.value}' is already registered."
            )
        self._providers[provider.name] = provider

    def get(self, provider_name: OAuthProviderName) -> OAuthProvider:
        try:
            return self._providers[provider_name]
        except KeyError as exc:
            raise LookupError(
                f"OAuth provider '{provider_name.value}' is not registered."
            ) from exc

    def configured(self) -> tuple[OAuthProviderName, ...]:
        return tuple(
            name
            for name, provider in self._providers.items()
            if provider.is_configured()
        )

    def registered(self) -> tuple[OAuthProviderName, ...]:
        return tuple(self._providers)
