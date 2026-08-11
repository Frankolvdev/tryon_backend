from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.models.user import User
from app.schemas.body_proportion_tool import (
    BodyProportionGenerationResponse, BodyProportionHealthResponse,
    BodyProportionInterpolateRequest, BodyProportionNextRequest,
    BodyProportionPresetCreate, BodyProportionPresetListResponse,
    BodyProportionPresetResponse, BodyProportionPresetUpdate,
    BodyProportionRecalculateRequest, BodyProportionRecalculateResponse,
    BodyProportionSeedResponse, BodyProportionStorageOptionsResponse, BodyProportionResetResponse,
    BodyProportionWorkflowConfigResponse, BodyProportionWorkflowConfigUpsert,
)
from app.services.body_proportion_tool_service import body_proportion_tool_service
from app.services.comfyui_local_adapter_service import comfyui_local_adapter_service

router = APIRouter(prefix="/tools-generation/body-proportions")


def _bad_request(error: Exception):
    if isinstance(error, LookupError):
        raise HTTPException(status_code=404, detail=str(error)) from error
    raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/health", response_model=BodyProportionHealthResponse)
def health(current_admin: User = Depends(admin_guard)):
    return {"local_only": True, "comfyui": comfyui_local_adapter_service.health()}


@router.get("/storage-options", response_model=BodyProportionStorageOptionsResponse)
def storage_options(db: Session = Depends(get_db), current_admin: User = Depends(admin_guard)):
    try: return body_proportion_tool_service.storage_options(db)
    except Exception as error: _bad_request(error)


@router.get("/config/{sex}", response_model=BodyProportionWorkflowConfigResponse)
def get_config(sex: str, db: Session = Depends(get_db), current_admin: User = Depends(admin_guard)):
    try: return body_proportion_tool_service.get_config(db, sex)
    except Exception as error: _bad_request(error)


@router.put("/config/{sex}", response_model=BodyProportionWorkflowConfigResponse)
def put_config(data: BodyProportionWorkflowConfigUpsert, sex: str, db: Session = Depends(get_db), current_admin: User = Depends(admin_guard)):
    try: return body_proportion_tool_service.upsert_config(db, sex, data)
    except Exception as error: _bad_request(error)




@router.delete("/reset/{sex}", response_model=BodyProportionResetResponse)
def reset_tool(sex: str, db: Session = Depends(get_db), current_admin: User = Depends(admin_guard)):
    try:
        return body_proportion_tool_service.reset_tool(db, sex)
    except Exception as error:
        _bad_request(error)

@router.post("/presets/seed-defaults", response_model=BodyProportionSeedResponse)
def seed_defaults(sex: str = "woman", db: Session = Depends(get_db), current_admin: User = Depends(admin_guard)):
    try: return body_proportion_tool_service.seed_defaults(db, sex)
    except Exception as error: _bad_request(error)


@router.post("/presets/recalculate-defaults", response_model=BodyProportionRecalculateResponse)
def recalc_defaults(data: BodyProportionRecalculateRequest, sex: str = "woman", db: Session = Depends(get_db), current_admin: User = Depends(admin_guard)):
    try: return body_proportion_tool_service.recalculate_defaults(db, sex, data.include_ready)
    except Exception as error: _bad_request(error)


@router.get("/presets", response_model=BodyProportionPresetListResponse)
def list_presets(sex: str = "woman", db: Session = Depends(get_db), current_admin: User = Depends(admin_guard)):
    try:
        rows = body_proportion_tool_service.list_presets(db, sex)
        return {"items": [body_proportion_tool_service.response(db, row) for row in rows], "total": len(rows)}
    except Exception as error: _bad_request(error)


@router.post("/presets", response_model=BodyProportionPresetResponse, status_code=status.HTTP_201_CREATED)
def create_preset(data: BodyProportionPresetCreate, db: Session = Depends(get_db), current_admin: User = Depends(admin_guard)):
    try:
        row = body_proportion_tool_service.create_preset(db, data)
        return body_proportion_tool_service.response(db, row)
    except Exception as error: _bad_request(error)


@router.post("/presets/{preset_id}/synchronize-rules", response_model=BodyProportionPresetResponse)
def synchronize_preset_rules(preset_id: int, db: Session = Depends(get_db), current_admin: User = Depends(admin_guard)):
    try:
        row = body_proportion_tool_service.synchronize_preset_with_rules(db, preset_id)
        return body_proportion_tool_service.response(db, row)
    except Exception as error:
        _bad_request(error)


@router.post("/presets/{preset_id}/next", response_model=BodyProportionPresetResponse, status_code=status.HTTP_201_CREATED)
def create_next(preset_id: int, data: BodyProportionNextRequest, db: Session = Depends(get_db), current_admin: User = Depends(admin_guard)):
    try:
        row = body_proportion_tool_service.create_next(db, preset_id, data.display_name)
        return body_proportion_tool_service.response(db, row)
    except Exception as error: _bad_request(error)


@router.post("/presets/interpolate", response_model=BodyProportionPresetResponse, status_code=status.HTTP_201_CREATED)
def interpolate(data: BodyProportionInterpolateRequest, db: Session = Depends(get_db), current_admin: User = Depends(admin_guard)):
    try:
        row = body_proportion_tool_service.interpolate(db, data)
        return body_proportion_tool_service.response(db, row)
    except Exception as error: _bad_request(error)


@router.patch("/presets/{preset_id}", response_model=BodyProportionPresetResponse)
def update_preset(preset_id: int, data: BodyProportionPresetUpdate, db: Session = Depends(get_db), current_admin: User = Depends(admin_guard)):
    try:
        row = body_proportion_tool_service.update_preset(db, preset_id, data)
        return body_proportion_tool_service.response(db, row)
    except Exception as error: _bad_request(error)


@router.delete("/presets/{preset_id}")
def delete_preset(preset_id: int, db: Session = Depends(get_db), current_admin: User = Depends(admin_guard)):
    try:
        body_proportion_tool_service.delete_preset(db, preset_id)
        return {"deleted": True, "preset_id": preset_id}
    except Exception as error: _bad_request(error)


@router.post("/presets/{preset_id}/generate", response_model=BodyProportionGenerationResponse)
def generate_preset(preset_id: int, db: Session = Depends(get_db), current_admin: User = Depends(admin_guard)):
    try:
        row, prompt_id, provider, overwritten = body_proportion_tool_service.generate(db, preset_id)
        return {"preset": body_proportion_tool_service.response(db, row), "prompt_id": prompt_id,
                "storage_provider": provider, "overwritten": overwritten}
    except Exception as error: _bad_request(error)
