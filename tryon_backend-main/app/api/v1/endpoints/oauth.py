from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.common.exceptions import AppException
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


def _oauth_error_code(exc: AppException) -> str:
    message = exc.message.lower()
    if "administrative account" in message:
        return "admin_account"
    if "terms and conditions" in message or "accept the terms" in message:
        return "terms_not_accepted"
    if "minimum age" in message or "confirm that you meet" in message:
        return "age_not_confirmed"
    if "registration is currently disabled" in message:
        return "registration_disabled"
    if "verified email" in message:
        return "email_not_verified"
    if "different account linked" in message:
        return "provider_already_linked"
    if "state" in message:
        return "invalid_state"
    if "not available" in message or "not configured" in message:
        return "provider_unavailable"
    if "temporarily unavailable" in message:
        return "service_unavailable"
    return exc.error_code.lower()


def _callback_error_response(
    *,
    provider: OAuthProviderName,
    state: str | None,
    error: str,
    description: str,
) -> RedirectResponse:
    frontend_uri = oauth_flow_service.callback_frontend_uri_from_state(state, provider)
    target = oauth_flow_service.callback_error_redirect(
        frontend_uri,
        error=error,
        error_description=description,
    )
    return RedirectResponse(url=target, status_code=302)


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
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    # OAuth providers return errors such as access_denied directly to this
    # callback. Convert them to an AppWeb screen instead of exposing JSON.
    if error:
        return _callback_error_response(
            provider=provider,
            state=state,
            error=error,
            description=error_description or "The OAuth authorization was not completed.",
        )

    if not code:
        return _callback_error_response(
            provider=provider,
            state=state,
            error="missing_code",
            description="The OAuth provider did not return an authorization code.",
        )

    if not state:
        return _callback_error_response(
            provider=provider,
            state=None,
            error="missing_state",
            description="The OAuth authorization state is missing or invalid.",
        )

    callback_uri = str(request.url_for("oauth_callback", provider=provider.value))
    try:
        frontend_redirect_uri, grant = await oauth_flow_service.callback(
            db,
            provider_name=provider,
            code=code,
            state=state,
            backend_callback_uri=callback_uri,
        )
    except AppException as exc:
        return _callback_error_response(
            provider=provider,
            state=state,
            error=_oauth_error_code(exc),
            description=exc.message,
        )
    except Exception:
        # Do not leak provider tokens, traces, or internal details to the browser.
        return _callback_error_response(
            provider=provider,
            state=state,
            error="oauth_callback_failed",
            description="We could not complete the OAuth login. Please try again.",
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
