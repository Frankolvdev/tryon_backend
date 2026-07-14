from pydantic import BaseModel


class OAuthProviderResponse(BaseModel):
    provider: str
    enabled: bool
    configured: bool
    authorization_url: str | None = None
    redirect_uri: str | None = None


class OAuthProvidersResponse(BaseModel):
    providers: list[OAuthProviderResponse]