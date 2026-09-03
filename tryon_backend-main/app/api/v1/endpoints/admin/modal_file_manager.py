import os
import tempfile
from pathlib import Path

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
    # Modal model files can be several GB. Never buffer the complete request in
    # RAM (`await request.body()`): stream it to a temporary file first, then
    # let the Modal CLI upload that file. This route is intentionally isolated
    # from Docker/RunPod/Beam file managers.
    from urllib.parse import unquote

    filename = unquote(request.headers.get("x-upload-filename") or "upload.bin")
    safe_filename = Path(filename).name or "upload.bin"
    fd, tmp_name = tempfile.mkstemp(
        prefix="tryon-modal-upload-",
        suffix="-" + safe_filename,
    )
    os.close(fd)
    size = 0
    try:
        with open(tmp_name, "wb") as out:
            async for chunk in request.stream():
                if chunk:
                    out.write(chunk)
                    size += len(chunk)
        return call(
            S.upload_file_path,
            db,
            volume,
            path,
            filename,
            Path(tmp_name),
            size,
            overwrite,
        )
    finally:
        Path(tmp_name).unlink(missing_ok=True)


@router.get("/download")
def download(volume: str, path: str, db: Session = Depends(get_db)):
    data = call(S.download_bytes, db, volume, path)
    name = path.replace("\\", "/").split("/")[-1]
    return Response(data, media_type="application/octet-stream", headers={"Content-Disposition": f'attachment; filename="{name}"'})
