from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.common.exceptions import ConflictException, NotFoundException
from app.models.user import User
from app.repositories.tryon_job_repository import tryon_job_repository
from app.schemas.comfyui import (
    ComfyUIRunWorkflowRequest,
    ComfyUIRunWorkflowResponse,
    ComfyUITryOnTestRequest,
    ComfyUITryOnTestResponse,
    ComfyUIWorkflowListResponse,
    ComfyUIWorkflowValidateRequest,
    ComfyUIWorkflowValidateResponse,
)
from app.services.comfyui_tryon_service import comfyui_tryon_service
from app.services.comfyui_workflow_service import comfyui_workflow_service
from app.services.tryon_service import tryon_service

router = APIRouter()


@router.get("/comfyui/workflows", response_model=ComfyUIWorkflowListResponse)
def list_comfyui_workflows(
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return ComfyUIWorkflowListResponse(
        workflows=comfyui_workflow_service.list_workflows(db),
    )


@router.post("/comfyui/workflows/validate", response_model=ComfyUIWorkflowValidateResponse)
def validate_comfyui_workflow(
    data: ComfyUIWorkflowValidateRequest,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    workflows = comfyui_workflow_service.list_workflows(db)

    if data.workflow_name not in workflows:
        return ComfyUIWorkflowValidateResponse(
            workflow_name=data.workflow_name,
            exists=False,
            valid=False,
            missing_nodes=data.required_nodes,
            available_nodes_count=0,
        )

    workflow = comfyui_workflow_service.load_workflow(
        db=db,
        workflow_name=data.workflow_name,
    )

    missing_nodes = [
        node_id
        for node_id in data.required_nodes
        if node_id not in workflow
    ]

    return ComfyUIWorkflowValidateResponse(
        workflow_name=data.workflow_name,
        exists=True,
        valid=len(missing_nodes) == 0,
        missing_nodes=missing_nodes,
        available_nodes_count=len(workflow.keys()),
    )


@router.post("/comfyui/run-workflow", response_model=ComfyUIRunWorkflowResponse)
def run_comfyui_workflow(
    data: ComfyUIRunWorkflowRequest,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    result = comfyui_workflow_service.run_workflow(
        db=db,
        workflow_name=data.workflow_name,
        patches=data.patches,
        client_id=data.client_id,
        wait_for_result=data.wait_for_result,
    )

    return ComfyUIRunWorkflowResponse(**result)


@router.post("/comfyui/test-tryon", response_model=ComfyUITryOnTestResponse)
def test_comfyui_tryon_job(
    data: ComfyUITryOnTestRequest,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    job = tryon_job_repository.get_by_id(db, data.tryon_job_id)

    if not job:
        raise NotFoundException("Try-on job not found.")

    try:
        result_file = comfyui_tryon_service.execute_tryon_job(
            db=db,
            job=job,
        )

        return ComfyUITryOnTestResponse(
            tryon_job_id=job.id,
            status="completed",
            result_file_id=result_file.id,
            error_message=None,
        )

    except Exception as error:
        return ComfyUITryOnTestResponse(
            tryon_job_id=job.id,
            status="failed",
            result_file_id=None,
            error_message=str(error),
        )


@router.post("/comfyui/process-tryon/{tryon_job_id}", response_model=ComfyUITryOnTestResponse)
def process_comfyui_tryon_job(
    tryon_job_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    job = tryon_service.process_comfyui_tryon_job(
        db=db,
        job_id=tryon_job_id,
    )

    return ComfyUITryOnTestResponse(
        tryon_job_id=job.id,
        status=job.status,
        result_file_id=job.result_file_id,
        error_message=job.error_message,
    )