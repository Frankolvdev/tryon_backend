from sqlalchemy.orm import Session

from app.schemas.oauth import OAuthProviderName
from app.services.oauth.config import OAUTH_PROVIDER_DEFINITIONS, load_oauth_provider_config
from app.services.oauth.providers.google import GoogleOAuthProvider
from app.services.oauth.registry import OAuthProviderRegistry


def build_oauth_provider_registry(db: Session) -> OAuthProviderRegistry:
    """Build the provider registry from integration settings stored in DB."""

    registry = OAuthProviderRegistry()

    for definition in OAUTH_PROVIDER_DEFINITIONS:
        runtime = load_oauth_provider_config(db, definition)

        if definition.name == OAuthProviderName.GOOGLE:
            registry.register(
                GoogleOAuthProvider(
                    client_id=runtime.client_id,
                    client_secret=runtime.client_secret,
                )
            )

    return registry
