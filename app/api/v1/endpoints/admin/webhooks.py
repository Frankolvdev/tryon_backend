from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.common.responses import SuccessResponse
from app.models.user import User
from app.schemas.webhook import (
    WebhookDeliveryResponse,
    WebhookEndpointCreate,
    WebhookEndpointCreateResponse,
    WebhookEndpointResponse,
    WebhookEndpointUpdate,
    WebhookEventCreate,
    WebhookEventResponse,
    WebhookEventRetryRequest,
    WebhookTestRequest,
)
from app.services.audit_service import audit_service
from app.services.webhook_service import webhook_service

router = APIRouter()


@router.get("/webhook-endpoints", response_model=list[WebhookEndpointResponse])
def list_webhook_endpoints(
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
):
    return webhook_service.list_endpoints(
        db=db,
        skip=skip,
        limit=limit,
    )


@router.post("/webhook-endpoints", response_model=WebhookEndpointCreateResponse)
def create_webhook_endpoint(
    data: WebhookEndpointCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    result = webhook_service.create_endpoint(
        db=db,
        data=data,
        created_by_user=current_admin,
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_webhook_endpoint_created",
        entity_type="webhook_endpoint",
        entity_id=str(result.endpoint.id),
        description=f"Admin created webhook endpoint {result.endpoint.name}.",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return result


@router.patch("/webhook-endpoints/{endpoint_id}", response_model=WebhookEndpointResponse)
def update_webhook_endpoint(
    endpoint_id: int,
    data: WebhookEndpointUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    endpoint = webhook_service.update_endpoint(
        db=db,
        endpoint_id=endpoint_id,
        data=data,
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_webhook_endpoint_updated",
        entity_type="webhook_endpoint",
        entity_id=str(endpoint.id),
        description=f"Admin updated webhook endpoint {endpoint.name}.",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return endpoint


@router.post("/webhook-endpoints/{endpoint_id}/test", response_model=WebhookEventResponse)
def test_webhook_endpoint(
    endpoint_id: int,
    data: WebhookTestRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    event = webhook_service.create_event(
        db=db,
        data=WebhookEventCreate(
            event_type="webhook.test",
            source="admin",
            entity_type="webhook_endpoint",
            entity_id=str(endpoint_id),
            payload=data.payload,
            max_attempts=1,
        ),
    )

    delivered = webhook_service.deliver_event(
        db=db,
        event_id=event.id,
        force=True,
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_webhook_endpoint_tested",
        entity_type="webhook_endpoint",
        entity_id=str(endpoint_id),
        description="Admin tested webhook endpoint.",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return delivered


@router.get("/webhook-events", response_model=list[WebhookEventResponse])
def list_webhook_events(
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
):
    return webhook_service.list_events(
        db=db,
        skip=skip,
        limit=limit,
    )


@router.post("/webhook-events", response_model=WebhookEventResponse)
def create_webhook_event(
    data: WebhookEventCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    event = webhook_service.create_event(
        db=db,
        data=data,
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_webhook_event_created",
        entity_type="webhook_event",
        entity_id=str(event.id),
        description=f"Admin created webhook event {event.event_type}.",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return event


@router.post("/webhook-events/{event_id}/deliver", response_model=WebhookEventResponse)
def deliver_webhook_event(
    event_id: int,
    data: WebhookEventRetryRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    event = webhook_service.deliver_event(
        db=db,
        event_id=event_id,
        force=data.force,
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_webhook_event_delivered",
        entity_type="webhook_event",
        entity_id=str(event.id),
        description=f"Admin manually delivered webhook event {event.event_type}.",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return event


@router.get(
    "/webhook-events/{event_id}/deliveries",
    response_model=list[WebhookDeliveryResponse],
)
def list_webhook_event_deliveries(
    event_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
):
    return webhook_service.list_deliveries_by_event(
        db=db,
        event_id=event_id,
        skip=skip,
        limit=limit,
    )


@router.post("/webhooks/process-pending", response_model=SuccessResponse)
def process_pending_webhooks(
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    result = webhook_service.process_pending_events(db)

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_webhooks_pending_processed",
        entity_type="webhook_events",
        entity_id=None,
        description="Admin manually processed pending webhook events.",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return SuccessResponse(
        message=f"Processed pending webhooks. Delivered: {result['processed']}, skipped: {result['skipped']}.",
    )