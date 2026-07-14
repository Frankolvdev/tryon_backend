from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.models.user import User
from app.schemas.email import EmailSendResponse, EmailSendTestRequest
from app.schemas.oauth import OAuthProvidersResponse
from app.services.oauth_provider_service import oauth_provider_service
from app.services.smtp_email_service import smtp_email_service

router = APIRouter()


@router.post("/integrations/smtp/test-email", response_model=EmailSendResponse)
def send_smtp_test_email(
    data: EmailSendTestRequest,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    smtp_email_service.send_email(
        db=db,
        to_email=data.to_email,
        subject=data.subject,
        body=data.body,
    )

    return EmailSendResponse(
        sent=True,
        message="Test email sent successfully.",
    )


@router.get("/integrations/oauth/providers", response_model=OAuthProvidersResponse)
def list_oauth_providers(
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return OAuthProvidersResponse(
        providers=oauth_provider_service.list_providers(db),
    )