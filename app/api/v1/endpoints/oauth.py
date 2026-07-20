from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.schemas.auth import TokenResponse
from app.schemas.oauth import (
    OAuthAuthorizationResponse,
    OAuthGrantExchangeRequest,
    OAuthPublicProvidersResponse,
    OAuthProviderName,
    OAuthStartRequest,
)
from app.services.oauth.flow import oauth_flow_service
from app.services.oauth_provider_service import oauth_provider_service


router = APIRouter()


@router.get("/providers", response_model=OAuthPublicProvidersResponse)
def list_oauth_providers(
    db: Session = Depends(get_db),
):
    return OAuthPublicProvidersResponse(
        providers=oauth_provider_service.list_public_providers(db)
    )


@router.post("/{provider}/start", response_model=OAuthAuthorizationResponse)
def start_oauth(
    provider: OAuthProviderName,
    data: OAuthStartRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    callback_uri = str(request.url_for("oauth_callback", provider=provider.value))
    authorization_url, state = oauth_flow_service.authorization_url(
        db,
        provider_name=provider,
        backend_callback_uri=callback_uri,
        frontend_redirect_uri=str(data.redirect_uri),
        terms_accepted=data.terms_accepted,
        terms_version=data.terms_version,
        age_confirmed=data.age_confirmed,
    )
    return OAuthAuthorizationResponse(
        authorization_url=authorization_url,
        state=state,
        provider=provider,
    )


@router.get("/{provider}/callback", name="oauth_callback")
async def oauth_callback(
    provider: OAuthProviderName,
    request: Request,
    code: str = Query(min_length=1),
    state: str = Query(min_length=32),
    db: Session = Depends(get_db),
):
    callback_uri = str(request.url_for("oauth_callback", provider=provider.value))
    frontend_redirect_uri, grant = await oauth_flow_service.callback(
        db,
        provider_name=provider,
        code=code,
        state=state,
        backend_callback_uri=callback_uri,
    )
    return RedirectResponse(
        url=oauth_flow_service.callback_redirect(frontend_redirect_uri, grant),
        status_code=302,
    )


@router.post("/exchange", response_model=TokenResponse)
def exchange_oauth_grant(
    data: OAuthGrantExchangeRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    return oauth_flow_service.exchange_grant(
        db,
        grant=data.code,
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
    )
