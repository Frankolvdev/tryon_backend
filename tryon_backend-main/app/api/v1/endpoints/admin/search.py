from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.models.user import User
from app.schemas.search import AdvancedSearchRequest, SearchResponse
from app.services.search_service import search_service

router = APIRouter()


@router.get("/search", response_model=SearchResponse)
def global_search(
    q: str = Query(..., min_length=1),
    entities: list[str] | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return search_service.search(
        db=db,
        query=q,
        entities=entities,
        page=page,
        page_size=page_size,
        filters={},
    )


@router.post("/search/advanced", response_model=SearchResponse)
def advanced_search(
    data: AdvancedSearchRequest,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return search_service.search(
        db=db,
        query=data.query,
        entities=data.entities,
        page=data.page,
        page_size=data.page_size,
        filters=data.filters,
    )