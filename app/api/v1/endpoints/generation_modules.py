from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.auth_guard import auth_guard
from app.common.exceptions import NotFoundException
from app.models.user import User
from app.common.enums import UserRole
from app.common.generation_module_enums import GenerationExecutionEngine
from app.schemas.generation_module import GenerationModuleListResponse, GenerationModuleResponse
from app.schemas.generation_module_runtime import GenerationModuleExecutionCreate, GenerationModuleExecutionResponse
from app.services.generation_module_runtime_service import generation_module_runtime_service
from app.services.generation_module_upload_service import generation_module_upload_service
from app.services.generation_module_service import generation_module_service
from app.services.audit_service import audit_service
from app.services.generation_execution_media_service import generation_execution_media_service
from app.services.generation_execution_state_contract import generation_execution_state_contract

router = APIRouter()


@router.get("/", response_model=GenerationModuleListResponse)
def list_available_generation_modules(
    category: str | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_guard),
):
    return generation_module_service.list_modules(
        db, category=category, is_active=True, skip=skip, limit=limit
    )


@router.get("/executions/{execution_id}/status", response_model=GenerationModuleExecutionResponse)
def get_my_generation_execution(
    execution_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_guard),
):
    execution = generation_module_runtime_service.get_for_user(execution_id, user_id=current_user.id)
    return generation_execution_media_service.hydrate(db, execution)




@router.post("/executions/{execution_id}/settle-pending-billing", response_model=GenerationModuleExecutionResponse)
def settle_my_pending_generation_billing(
    execution_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_guard),
):
    execution = generation_module_runtime_service.settle_pending_billing(
        db, execution_id, user_id=current_user.id
    )
    return generation_execution_media_service.hydrate(db, execution)


@router.post("/executions/{execution_id}/cancel", response_model=GenerationModuleExecutionResponse)
def cancel_my_generation_execution(
    execution_id: UUID,
    current_user: User = Depends(auth_guard),
):
    return generation_module_runtime_service.cancel_for_user(execution_id, user_id=current_user.id)


from app.schemas.generation_module_operations import GenerationExecutionListResponse, GenerationExecutionRetryRequest


@router.get("/active-executions", response_model=GenerationExecutionListResponse)
def list_my_active_generation_executions(
    module_id: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_guard),
):
    items, _ = generation_module_runtime_service.list(
        user_id=current_user.id, module_id=module_id, skip=0, limit=limit
    )
    active = [item for item in items if generation_execution_state_contract.is_active_for_client(item)]
    return GenerationExecutionListResponse(items=generation_execution_media_service.hydrate_many(db, active), total=len(active), skip=0, limit=limit)


@router.get("/execution-history", response_model=GenerationExecutionListResponse)
def list_my_generation_executions(module_id: int | None = Query(default=None), status: str | None = Query(default=None), skip: int = Query(default=0, ge=0), limit: int = Query(default=100, ge=1, le=100), db: Session = Depends(get_db), current_user: User = Depends(auth_guard)):
    items, total = generation_module_runtime_service.list(user_id=current_user.id, module_id=module_id, status=status, skip=skip, limit=limit)
    return GenerationExecutionListResponse(items=generation_execution_media_service.hydrate_many(db, items), total=total, skip=skip, limit=limit)



@router.get("/{module_id}", response_model=GenerationModuleResponse)
def get_available_generation_module(
    module_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_guard),
):
    module = generation_module_service.get_response(db, module_id=module_id)
    if not module.is_active:
        raise NotFoundException("Generation module not found.")
    return module


@router.post("/{module_id}/executions", response_model=GenerationModuleExecutionResponse, status_code=202)
async def execute_available_generation_module(
    module_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_guard),
):
    # The published module selects its default engine; security policy validates whether end users may run it.
    payload = await generation_module_upload_service.parse_execution_request(
        db, module_id=module_id, request=request, user_id=current_user.id,
    )
    accounting_mode = "commercial"
    if current_user.role == UserRole.OWNER.value:
        # Owner uses the same module/workflow/history, but execution is forced
        # to the private Windows/Pinokio provider and never enters finance.
        payload.engine = GenerationExecutionEngine.OWNER_LOCAL
        accounting_mode = "owner_private"
    result = generation_module_runtime_service.create(
        db,
        module_id=module_id,
        data=payload,
        user_id=current_user.id,
        user_role=current_user.role,
        accounting_mode=accounting_mode,
    )
    audit_service.create_log(db, actor_user_id=current_user.id, action="generation_execution_started", entity_type="generation_execution", entity_id=str(result.id), description=f"Started generation for module {module_id}.", ip_address=request.client.host if request.client else None, user_agent=request.headers.get("user-agent"))
    return generation_execution_media_service.hydrate(db, result)

@router.post("/executions/{execution_id}/retry", response_model=GenerationModuleExecutionResponse, status_code=202)
def retry_my_generation_execution(execution_id: UUID, data: GenerationExecutionRetryRequest, db: Session = Depends(get_db), current_user: User = Depends(auth_guard)):
    return generation_module_runtime_service.retry(db, execution_id, user_id=current_user.id, engine=data.engine)
