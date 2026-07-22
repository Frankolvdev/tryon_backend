from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.common.generation_module_enums import GenerationExecutionEngine
from app.models.user import User
from app.schemas.generation_module import (
    GenerationModuleCreate,
    GenerationModuleListResponse,
    GenerationModuleResponse,
    GenerationModuleUpdate,
)
from app.schemas.generation_module_authoring import (
    GenerationModuleStepsReorderRequest,
    PythonStepCreateRequest,
    PythonStepUpdateRequest,
    WorkflowStepBindingsUpdate,
    WorkflowStepImportRequest,
    WorkflowValidationResponse,
)
from app.services.audit_service import audit_service
from app.services.generation_module_service import generation_module_service
from app.services.generation_module_authoring_service import (
    generation_module_authoring_service,
)

router = APIRouter()


@router.get("/generation-modules", response_model=GenerationModuleListResponse)
def list_generation_modules(
    key: str | None = Query(default=None),
    category: str | None = Query(default=None),
    engine: GenerationExecutionEngine | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    search: str | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return generation_module_service.list_modules(
        db,
        key=key,
        category=category,
        engine=engine.value if engine else None,
        is_active=is_active,
        search=search,
        skip=skip,
        limit=limit,
    )


@router.get("/generation-modules/{module_id}", response_model=GenerationModuleResponse)
def get_generation_module(
    module_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return generation_module_service.get_response(db, module_id=module_id)


@router.post(
    "/generation-modules", response_model=GenerationModuleResponse, status_code=201
)
def create_generation_module(
    data: GenerationModuleCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    result = generation_module_service.create(
        db, data=data, created_by_user_id=current_admin.id
    )
    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_generation_module_created",
        entity_type="generation_module",
        entity_id=str(result.id),
        description=f"Created generation module {result.key} version {result.version}.",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return result


@router.patch(
    "/generation-modules/{module_id}", response_model=GenerationModuleResponse
)
def update_generation_module(
    module_id: int,
    data: GenerationModuleUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    result = generation_module_service.update(db, module_id=module_id, data=data)
    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_generation_module_updated",
        entity_type="generation_module",
        entity_id=str(module_id),
        description=f"Updated generation module {module_id}.",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return result


@router.delete("/generation-modules/{module_id}", status_code=204)
def delete_generation_module(
    module_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    generation_module_service.delete(db, module_id=module_id)
    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_generation_module_deleted",
        entity_type="generation_module",
        entity_id=str(module_id),
        description=f"Deleted generation module {module_id}.",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return Response(status_code=204)


@router.post(
    "/generation-modules/workflows/validate",
    response_model=WorkflowValidationResponse,
)
def validate_generation_module_workflow(
    workflow_json: dict,
    current_admin: User = Depends(admin_guard),
):
    return generation_module_authoring_service.validate_workflow(workflow_json)


@router.post(
    "/generation-modules/{module_id}/steps/workflow",
    response_model=GenerationModuleResponse,
    status_code=201,
)
def import_generation_module_workflow_step(
    module_id: int,
    data: WorkflowStepImportRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    result = generation_module_authoring_service.import_workflow_step(
        db, module_id=module_id, data=data
    )
    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_generation_module_workflow_imported",
        entity_type="generation_module",
        entity_id=str(module_id),
        description=f"Imported workflow step {data.key} into generation module {module_id}.",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return result


@router.patch(
    "/generation-modules/{module_id}/steps/{step_id}/workflow-bindings",
    response_model=GenerationModuleResponse,
)
def update_generation_module_workflow_bindings(
    module_id: int,
    step_id: int,
    data: WorkflowStepBindingsUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    result = generation_module_authoring_service.update_workflow_bindings(
        db, module_id=module_id, step_id=step_id, data=data
    )
    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_generation_module_workflow_bindings_updated",
        entity_type="generation_module_step",
        entity_id=str(step_id),
        description=f"Updated workflow bindings for generation module step {step_id}.",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return result


@router.post(
    "/generation-modules/{module_id}/steps/python",
    response_model=GenerationModuleResponse,
    status_code=201,
)
def create_generation_module_python_step(
    module_id: int,
    data: PythonStepCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    result = generation_module_authoring_service.create_python_step(
        db, module_id=module_id, data=data
    )
    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_generation_module_python_step_created",
        entity_type="generation_module",
        entity_id=str(module_id),
        description=f"Created Python step {data.key} in generation module {module_id}.",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return result


@router.patch(
    "/generation-modules/{module_id}/steps/{step_id}/python",
    response_model=GenerationModuleResponse,
)
def update_generation_module_python_step(
    module_id: int,
    step_id: int,
    data: PythonStepUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    result = generation_module_authoring_service.update_python_step(
        db, module_id=module_id, step_id=step_id, data=data
    )
    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_generation_module_python_step_updated",
        entity_type="generation_module_step",
        entity_id=str(step_id),
        description=f"Updated Python generation module step {step_id}.",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return result


@router.put(
    "/generation-modules/{module_id}/steps/reorder",
    response_model=GenerationModuleResponse,
)
def reorder_generation_module_steps(
    module_id: int,
    data: GenerationModuleStepsReorderRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    result = generation_module_authoring_service.reorder_steps(
        db, module_id=module_id, data=data
    )
    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_generation_module_steps_reordered",
        entity_type="generation_module",
        entity_id=str(module_id),
        description=f"Reordered steps for generation module {module_id}.",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return result


@router.delete(
    "/generation-modules/{module_id}/steps/{step_id}",
    response_model=GenerationModuleResponse,
)
def delete_generation_module_step(
    module_id: int,
    step_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    result = generation_module_authoring_service.delete_step(
        db, module_id=module_id, step_id=step_id
    )
    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_generation_module_step_deleted",
        entity_type="generation_module_step",
        entity_id=str(step_id),
        description=f"Deleted generation module step {step_id}.",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return result


# Generation module test runtime
from uuid import UUID
from app.schemas.generation_module_runtime import GenerationModuleExecutionCreate, GenerationModuleExecutionResponse
from app.services.generation_module_runtime_service import generation_module_runtime_service


@router.post("/generation-modules/{module_id}/executions", response_model=GenerationModuleExecutionResponse, status_code=202)
def execute_generation_module(
    module_id: int,
    data: GenerationModuleExecutionCreate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return generation_module_runtime_service.create(db, module_id=module_id, data=data)


@router.get("/generation-modules/executions/{execution_id}", response_model=GenerationModuleExecutionResponse)
def get_generation_module_execution(
    execution_id: UUID,
    current_admin: User = Depends(admin_guard),
):
    return generation_module_runtime_service.get(execution_id)


@router.post("/generation-modules/executions/{execution_id}/cancel", response_model=GenerationModuleExecutionResponse)
def cancel_generation_module_execution(
    execution_id: UUID,
    current_admin: User = Depends(admin_guard),
):
    return generation_module_runtime_service.cancel(execution_id)

@router.get("/generation-modules/runtime/health")
def generation_module_runtime_health(
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return generation_module_runtime_service.health(db)
