from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from app.api.v1.deps import get_db
from app.api.v1.guards.auth_guard import auth_guard
from app.models.user import User
from app.schemas.user_library import UserLibraryFileResponse, UserLibraryListResponse, UserLibraryUsageResponse
from app.services.user_library_service import user_library_service
router=APIRouter()

@router.get("", response_model=UserLibraryListResponse)
def list_library(search:str|None=Query(None), content_type:str|None=Query(None), limit:int=Query(100,ge=1,le=200), db:Session=Depends(get_db), current_user:User=Depends(auth_guard)):
    return user_library_service.list(db,current_user,search,content_type,limit)

@router.get("/usage", response_model=UserLibraryUsageResponse)
def usage(db:Session=Depends(get_db), current_user:User=Depends(auth_guard)):
    return user_library_service.usage(db,current_user.id)

@router.post("", response_model=UserLibraryFileResponse, status_code=status.HTTP_201_CREATED)
def upload(file:UploadFile=File(...), db:Session=Depends(get_db), current_user:User=Depends(auth_guard)):
    return user_library_service.upload(db,current_user,file)

@router.get("/{file_id}/content")
def content(file_id:int, db:Session=Depends(get_db), current_user:User=Depends(auth_guard)):
    item=user_library_service.get_owned(db,current_user,file_id)
    return RedirectResponse(user_library_service._url(db,item))

@router.delete("/{file_id}", status_code=204)
def delete(file_id:int, db:Session=Depends(get_db), current_user:User=Depends(auth_guard)):
    user_library_service.delete(db,current_user,file_id)

@router.delete("", status_code=200)
def clear(db:Session=Depends(get_db), current_user:User=Depends(auth_guard)):
    return {"deleted":user_library_service.clear(db,current_user)}
