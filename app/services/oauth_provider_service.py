from sqlalchemy.orm import Session

from app.services.oauth.config import (
    OAUTH_PROVIDER_DEFINITIONS,
    load_oauth_provider_config,
)


class OAuthProviderService:
    def list_public_providers(self, db: Session) -> list[dict]:
        providers: list[dict] = []

        for definition in OAUTH_PROVIDER_DEFINITIONS:
            runtime = load_oauth_provider_config(db, definition)
            providers.append(
                {
                    "provider": definition.name.value,
                    "enabled": runtime.enabled,
                    "configured": runtime.configured,
                    "available": bool(runtime.enabled and runtime.configured),
                }
            )

        return providers

    def list_providers(self, db: Session) -> list[dict]:
        providers: list[dict] = []

        for definition in OAUTH_PROVIDER_DEFINITIONS:
            runtime = load_oauth_provider_config(db, definition)
            providers.append(
                {
                    "provider": definition.integration_provider.value,
                    "enabled": runtime.enabled,
                    "configured": runtime.configured,
                    "authorization_url": runtime.build_authorization_url(),
                    "redirect_uri": runtime.redirect_uri,
                }
            )

        return providers


oauth_provider_service = OAuthProviderService()
