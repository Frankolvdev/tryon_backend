from enum import StrEnum

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl

from app.common.enums import IntegrationProvider


class OAuthProviderName(StrEnum):
    GOOGLE = "google"
    GITHUB = "github"
    FACEBOOK = "facebook"
    APPLE = "apple"


class OAuthProviderProfile(BaseModel):
    """Normalized profile returned by any supported OAuth provider."""

    provider: OAuthProviderName
    provider_user_id: str = Field(min_length=1, max_length=255)
    email: EmailStr | None = None
    email_verified: bool = False
    full_name: str | None = Field(default=None, max_length=255)
    username: str | None = Field(default=None, max_length=255)
    avatar_url: HttpUrl | None = None


class OAuthAuthorizationRequest(BaseModel):
    provider: OAuthProviderName
    redirect_uri: HttpUrl
    code_challenge: str | None = Field(default=None, min_length=43, max_length=128)
    code_challenge_method: str | None = Field(default=None, pattern="^(S256|plain)$")


class OAuthAuthorizationResponse(BaseModel):
    authorization_url: HttpUrl
    state: str = Field(min_length=32)
    provider: OAuthProviderName


class OAuthAccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    provider: OAuthProviderName
    provider_user_id: str
    provider_email: EmailStr | None = None
    provider_username: str | None = None
    provider_avatar_url: str | None = None
    email_verified: bool
    is_active: bool


class OAuthProviderConfigResponse(BaseModel):
    """Public configuration state for an OAuth integration.

    Secrets are never exposed. The provider value intentionally follows the
    existing IntegrationProvider enum used by the BackOffice.
    """

    provider: IntegrationProvider
    enabled: bool
    configured: bool
    authorization_url: str | None = None
    redirect_uri: str | None = None


class OAuthProvidersResponse(BaseModel):
    providers: list[OAuthProviderConfigResponse]




class OAuthPublicProviderRead(BaseModel):
    provider: OAuthProviderName
    enabled: bool
    configured: bool
    available: bool


class OAuthPublicProvidersResponse(BaseModel):
    providers: list[OAuthPublicProviderRead]


class OAuthStartRequest(BaseModel):
    redirect_uri: HttpUrl
    terms_accepted: bool = False
    terms_version: str | None = Field(default=None, max_length=100)
    age_confirmed: bool = False


class OAuthGrantExchangeRequest(BaseModel):
    code: str = Field(min_length=32, max_length=512)
