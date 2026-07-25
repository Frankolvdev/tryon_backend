from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.models.storage_file import StorageFile
from app.models.user import User
from app.schemas.user_library import UserLibraryAdminQuotaUpdate
from app.services.user_library_service import user_library_service
router=APIRouter()

@router.get("/user-library/summary")
def summary(db:Session=Depends(get_db), _:User=Depends(admin_guard)):
    used,count,users=db.execute(select(func.coalesce(func.sum(StorageFile.size_bytes),0),func.count(StorageFile.id),func.count(func.distinct(StorageFile.user_id))).where(StorageFile.object_key.like("user-library/%"))).one()
    return {"quota_mb":user_library_service.quota_bytes(db)//1024//1024,"used_bytes":int(used or 0),"file_count":int(count or 0),"user_count":int(users or 0)}

@router.put("/user-library/quota")
def set_quota(data:UserLibraryAdminQuotaUpdate, db:Session=Depends(get_db), _:User=Depends(admin_guard)):
    return {"quota_mb":user_library_service.set_quota_mb(db,data.quota_mb)}
