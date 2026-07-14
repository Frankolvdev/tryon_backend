from urllib.parse import urlencode

from sqlalchemy.orm import Session

from app.common.enums import IntegrationProvider
from app.services.integration_service import integration_service


class OAuthProviderService:
    def _provider_configs(self):
        return {
            IntegrationProvider.GOOGLE_OAUTH: {
                "authorization_base_url": "https://accounts.google.com/o/oauth2/v2/auth",
                "scope": "openid email profile",
            },
            IntegrationProvider.APPLE_OAUTH: {
                "authorization_base_url": "https://appleid.apple.com/auth/authorize",
                "scope": "name email",
            },
            IntegrationProvider.FACEBOOK_OAUTH: {
                "authorization_base_url": "https://www.facebook.com/v19.0/dialog/oauth",
                "scope": "email,public_profile",
            },
        }

    def list_providers(self, db: Session) -> list[dict]:
        providers = []

        for provider, provider_config in self._provider_configs().items():
            try:
                config = integration_service.get_config(db, provider)
                parsed_config = integration_service._parse_json(config.config_json)
                redirect_uri = parsed_config.get("redirect_uri")
                client_id = config.api_key

                authorization_url = None

                if config.is_enabled and client_id and redirect_uri:
                    params = {
                        "client_id": client_id,
                        "redirect_uri": redirect_uri,
                        "response_type": "code",
                        "scope": provider_config["scope"],
                    }

                    if provider == IntegrationProvider.GOOGLE_OAUTH:
                        params["access_type"] = "offline"
                        params["prompt"] = "consent"

                    authorization_url = (
                        provider_config["authorization_base_url"]
                        + "?"
                        + urlencode(params)
                    )

                providers.append(
                    {
                        "provider": provider.value,
                        "enabled": bool(config.is_enabled),
                        "configured": bool(client_id and redirect_uri),
                        "authorization_url": authorization_url,
                        "redirect_uri": redirect_uri,
                    }
                )

            except Exception:
                providers.append(
                    {
                        "provider": provider.value,
                        "enabled": False,
                        "configured": False,
                        "authorization_url": None,
                        "redirect_uri": None,
                    }
                )

        return providers


oauth_provider_service = OAuthProviderService()