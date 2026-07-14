from typing import Any

from pydantic import BaseModel, Field


class ComfyUIWorkflowPatch(BaseModel):
    node_id: str = Field(min_length=1)
    path: list[str | int] = Field(min_length=1)
    value: Any


class ComfyUIRunWorkflowRequest(BaseModel):
    workflow_name: str = Field(min_length=1)
    patches: list[ComfyUIWorkflowPatch] = []
    client_id: str | None = None
    wait_for_result: bool = True


class ComfyUIRunWorkflowResponse(BaseModel):
    prompt_id: str | None
    status: str
    images: list[dict[str, Any]] = []
    raw_queue_response: dict[str, Any] = {}
    raw_history: dict[str, Any] | None = None


class ComfyUIWorkflowListResponse(BaseModel):
    workflows: list[str]


class ComfyUIWorkflowValidateRequest(BaseModel):
    workflow_name: str = Field(min_length=1)
    required_nodes: list[str] = []


class ComfyUIWorkflowValidateResponse(BaseModel):
    workflow_name: str
    exists: bool
    valid: bool
    missing_nodes: list[str] = []
    available_nodes_count: int = 0


class ComfyUITryOnTestRequest(BaseModel):
    tryon_job_id: int


class ComfyUITryOnTestResponse(BaseModel):
    tryon_job_id: int
    status: str
    result_file_id: int | None = None
    error_message: str | None = None