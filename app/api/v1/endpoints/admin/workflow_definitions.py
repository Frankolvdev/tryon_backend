from fastapi import (
    APIRouter,
    Depends,
    Query,
    Request,
)
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import (
    admin_guard,
)
from app.models.user import User
from app.schemas.workflow_definition import (
    WorkflowDefinitionCreate,
    WorkflowDefinitionListResponse,
    WorkflowDefinitionResponse,
    WorkflowDefinitionUpdate,
    WorkflowVersionCreate,
)
from app.services.audit_service import (
    audit_service,
)
from app.services.workflow_definition_service import (
    workflow_definition_service,
)


router = APIRouter()


@router.get(
    "/workflow-definitions",
    response_model=WorkflowDefinitionListResponse,
)
def list_workflow_definitions(
    key: str | None = Query(default=None),
    category: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    is_default: bool | None = Query(default=None),
    search: str | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(
        default=100,
        ge=1,
        le=500,
    ),
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return (
        workflow_definition_service
        .list_workflows(
            db,
            key=key,
            category=category,
            is_active=is_active,
            is_default=is_default,
            search=search,
            skip=skip,
            limit=limit,
        )
    )


@router.get(
    "/workflow-definitions/{workflow_id}",
    response_model=WorkflowDefinitionResponse,
)
def get_workflow_definition(
    workflow_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return (
        workflow_definition_service
        .get_response(
            db,
            workflow_id=workflow_id,
        )
    )


@router.post(
    "/workflow-definitions",
    response_model=WorkflowDefinitionResponse,
    status_code=201,
)
def create_workflow_definition(
    data: WorkflowDefinitionCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    result = (
        workflow_definition_service
        .create(
            db,
            data=data,
            created_by_user_id=(
                current_admin.id
            ),
        )
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_workflow_created",
        entity_type="workflow_definition",
        entity_id=str(result.id),
        description=(
            f"Created workflow {result.key} "
            f"version {result.version}."
        ),
        ip_address=(
            request.client.host
            if request.client
            else None
        ),
        user_agent=request.headers.get(
            "user-agent"
        ),
    )

    return result


@router.patch(
    "/workflow-definitions/{workflow_id}",
    response_model=WorkflowDefinitionResponse,
)
def update_workflow_definition(
    workflow_id: int,
    data: WorkflowDefinitionUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    result = (
        workflow_definition_service
        .update(
            db,
            workflow_id=workflow_id,
            data=data,
        )
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_workflow_updated",
        entity_type="workflow_definition",
        entity_id=str(workflow_id),
        description=(
            f"Updated workflow {workflow_id}."
        ),
        ip_address=(
            request.client.host
            if request.client
            else None
        ),
        user_agent=request.headers.get(
            "user-agent"
        ),
    )

    return result


@router.post(
    "/workflow-definitions/{workflow_id}/versions",
    response_model=WorkflowDefinitionResponse,
    status_code=201,
)
def create_workflow_version(
    workflow_id: int,
    data: WorkflowVersionCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    result = (
        workflow_definition_service
        .create_version(
            db,
            workflow_id=workflow_id,
            data=data,
            created_by_user_id=(
                current_admin.id
            ),
        )
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_workflow_version_created",
        entity_type="workflow_definition",
        entity_id=str(result.id),
        description=(
            f"Created workflow {result.key} "
            f"version {result.version}."
        ),
        ip_address=(
            request.client.host
            if request.client
            else None
        ),
        user_agent=request.headers.get(
            "user-agent"
        ),
    )

    return result


@router.post(
    "/workflow-definitions/{workflow_id}/set-default",
    response_model=WorkflowDefinitionResponse,
)
def set_default_workflow(
    workflow_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    result = (
        workflow_definition_service
        .set_default(
            db,
            workflow_id=workflow_id,
        )
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_workflow_set_default",
        entity_type="workflow_definition",
        entity_id=str(workflow_id),
        description=(
            f"Set workflow {workflow_id} "
            "as category default."
        ),
        ip_address=(
            request.client.host
            if request.client
            else None
        ),
        user_agent=request.headers.get(
            "user-agent"
        ),
    )

    return result