from enum import StrEnum

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl


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
