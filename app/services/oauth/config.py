from dataclasses import dataclass
from urllib.parse import urlencode

from sqlalchemy.orm import Session

from app.common.enums import IntegrationProvider
from app.schemas.oauth import OAuthProviderName
from app.services.integration_service import integration_service


@dataclass(frozen=True, slots=True)
class OAuthProviderDefinition:
    name: OAuthProviderName
    integration_provider: IntegrationProvider
    authorization_base_url: str
    default_scope: str
    extra_authorization_params: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class OAuthProviderRuntimeConfig:
    definition: OAuthProviderDefinition
    enabled: bool
    client_id: str | None
    client_secret: str | None
    redirect_uri: str | None

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret and self.redirect_uri)

    def build_authorization_url(self) -> str | None:
        if not self.enabled or not self.configured:
            return None

        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": self.definition.default_scope,
        }
        params.update(dict(self.definition.extra_authorization_params))
        return f"{self.definition.authorization_base_url}?{urlencode(params)}"


OAUTH_PROVIDER_DEFINITIONS: tuple[OAuthProviderDefinition, ...] = (
    OAuthProviderDefinition(
        name=OAuthProviderName.GOOGLE,
        integration_provider=IntegrationProvider.GOOGLE_OAUTH,
        authorization_base_url="https://accounts.google.com/o/oauth2/v2/auth",
        default_scope="openid email profile",
        extra_authorization_params=(("access_type", "offline"), ("prompt", "consent")),
    ),
    OAuthProviderDefinition(
        name=OAuthProviderName.GITHUB,
        integration_provider=IntegrationProvider.GITHUB_OAUTH,
        authorization_base_url="https://github.com/login/oauth/authorize",
        default_scope="read:user user:email",
    ),
    OAuthProviderDefinition(
        name=OAuthProviderName.FACEBOOK,
        integration_provider=IntegrationProvider.FACEBOOK_OAUTH,
        authorization_base_url="https://www.facebook.com/v19.0/dialog/oauth",
        default_scope="email,public_profile",
    ),
    OAuthProviderDefinition(
        name=OAuthProviderName.APPLE,
        integration_provider=IntegrationProvider.APPLE_OAUTH,
        authorization_base_url="https://appleid.apple.com/auth/authorize",
        default_scope="name email",
        extra_authorization_params=(("response_mode", "form_post"),),
    ),
)


def load_oauth_provider_config(
    db: Session,
    definition: OAuthProviderDefinition,
) -> OAuthProviderRuntimeConfig:
    try:
        config = integration_service.get_config(db, definition.integration_provider)
        parsed = integration_service._parse_json(config.config_json)
        redirect_uri = parsed.get("redirect_uri")

        return OAuthProviderRuntimeConfig(
            definition=definition,
            enabled=bool(config.is_enabled),
            client_id=config.api_key or None,
            client_secret=config.api_secret or None,
            redirect_uri=(str(redirect_uri).strip() if redirect_uri else None),
        )
    except Exception:
        return OAuthProviderRuntimeConfig(
            definition=definition,
            enabled=False,
            client_id=None,
            client_secret=None,
            redirect_uri=None,
        )
