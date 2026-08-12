from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.api.v1.deps import get_db
from app.api.v1.guards.auth_guard import auth_guard
from app.models.user import User
from app.schemas.ai_model_profile import AiModelProfileBodyUpdate, AiModelProfileCreate, AiModelProfileResponse, BodyVariantCatalogResponse, BubbleButtVariantCatalogResponse
from app.services.ai_model_profile_service import ai_model_profile_service

router = APIRouter()

def _fail(error: Exception):
    if isinstance(error, LookupError): raise HTTPException(status_code=404, detail=str(error)) from error
    raise HTTPException(status_code=400, detail=str(error)) from error

@router.get("/body-variants", response_model=BodyVariantCatalogResponse)
def body_variants(sex: str = "woman", db: Session = Depends(get_db), current_user: User = Depends(auth_guard)):
    try:
        items = ai_model_profile_service.catalog(db, sex)
        return {"items": items, "total": len(items)}
    except Exception as error: _fail(error)

@router.get("/body-variants/{preset_id}/bubble-butt", response_model=BubbleButtVariantCatalogResponse)
def body_bubble_variants(
    preset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_guard),
):
    try:
        items = ai_model_profile_service.bubble_variants_for_body(db, preset_id)
        return {"items": items, "total": len(items)}
    except Exception as error:
        _fail(error)

@router.get("/", response_model=list[AiModelProfileResponse])
def list_models(db: Session = Depends(get_db), current_user: User = Depends(auth_guard)):
    return [ai_model_profile_service.response(db, row) for row in ai_model_profile_service.list_models(db, current_user.id)]

@router.post("/", response_model=AiModelProfileResponse)
def create_model(data: AiModelProfileCreate, db: Session = Depends(get_db), current_user: User = Depends(auth_guard)):
    try: return ai_model_profile_service.response(db, ai_model_profile_service.create(db, current_user.id, data.name, data.sex))
    except Exception as error: _fail(error)

@router.get("/{model_id}", response_model=AiModelProfileResponse)
def get_model(model_id: int, db: Session = Depends(get_db), current_user: User = Depends(auth_guard)):
    try: return ai_model_profile_service.response(db, ai_model_profile_service.get(db, current_user.id, model_id))
    except Exception as error: _fail(error)

@router.put("/{model_id}/body", response_model=AiModelProfileResponse)
def set_body(model_id: int, data: AiModelProfileBodyUpdate, db: Session = Depends(get_db), current_user: User = Depends(auth_guard)):
    try: return ai_model_profile_service.response(db, ai_model_profile_service.set_body(db, current_user.id, model_id, data.body_proportion_preset_id))
    except Exception as error: _fail(error)
