from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.services.modal_file_manager_service import ModalFileManagerError, ModalFileManagerService as S

router = APIRouter(prefix="/modal-file-manager", dependencies=[Depends(admin_guard)])


def call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except ModalFileManagerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/volumes")
def volumes(db: Session = Depends(get_db)):
    return {"items": call(S.list_volumes, db)}


@router.get("/browse")
def browse(volume: str = Query(...), path: str = "", db: Session = Depends(get_db)):
    return call(S.list_directory, db, volume, path)


@router.post("/directories")
def mkdir(payload: dict, db: Session = Depends(get_db)):
    return call(S.create_directory, db, str(payload.get("volume") or ""), str(payload.get("path") or ""))


@router.delete("/paths")
def delete(volume: str, path: str, db: Session = Depends(get_db)):
    return call(S.delete_path, db, volume, path)


@router.post("/upload-stream")
async def upload_stream(request: Request, volume: str = Query(...), path: str = Query(""), overwrite: bool = Query(True), db: Session = Depends(get_db)):
    filename = request.headers.get("x-upload-filename") or "upload.bin"
    from urllib.parse import unquote
    content = await request.body()
    return call(S.upload_bytes, db, volume, path, unquote(filename), content, overwrite)


@router.get("/download")
def download(volume: str, path: str, db: Session = Depends(get_db)):
    data = call(S.download_bytes, db, volume, path)
    name = path.replace("\\", "/").split("/")[-1]
    return Response(data, media_type="application/octet-stream", headers={"Content-Disposition": f'attachment; filename="{name}"'})
