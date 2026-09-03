from __future__ import annotations
import os, tempfile, shutil
from pathlib import Path
from urllib.parse import unquote
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.services.runpod_file_manager_service import RunPodFileManagerError as E, RunPodFileManagerService as S

router=APIRouter(prefix="/runpod-file-manager",dependencies=[Depends(admin_guard)])
def call(fn,*args,**kwargs):
    try:return fn(*args,**kwargs)
    except E as exc: raise HTTPException(status_code=400,detail=str(exc)) from exc
    except Exception as exc: raise HTTPException(status_code=502,detail=str(exc)) from exc
@router.get("/volumes")
def volumes(db:Session=Depends(get_db)):return {"items":call(S.list_volumes,db)}
@router.get("/browse")
def browse(volume:str=Query(...),path:str="",db:Session=Depends(get_db)):return call(S.list_directory,db,volume,path)
@router.post("/directories")
def mkdir(payload:dict,db:Session=Depends(get_db)):return call(S.create_directory,db,str(payload.get("volume") or ""),str(payload.get("path") or ""))
@router.delete("/paths")
def delete(volume:str,path:str,db:Session=Depends(get_db)):return call(S.delete_path,db,volume,path)
@router.post("/upload-stream")
async def upload(request:Request,volume:str=Query(...),path:str=Query(""),overwrite:bool=Query(True),db:Session=Depends(get_db)):
    filename=unquote(request.headers.get("x-upload-filename") or Path(path).name or "upload.bin")
    destination=str(path or filename).strip("/\\")
    fd,tmp_name=tempfile.mkstemp(prefix="tryon-runpod-upload-",suffix="-"+Path(filename).name); os.close(fd)
    size=0
    try:
        with open(tmp_name,"wb") as out:
            async for chunk in request.stream():
                if chunk: out.write(chunk); size+=len(chunk)
        with open(tmp_name,"rb") as source:
            return call(S.upload_file,db,volume,destination,source, size)
    finally: Path(tmp_name).unlink(missing_ok=True)
@router.get("/download")
def download(background_tasks:BackgroundTasks,volume:str,path:str,db:Session=Depends(get_db)):
    target=call(S.download_to_temp,db,volume,path); background_tasks.add_task(shutil.rmtree,target.parent,True) if target.parent.name.startswith("tryon-") else background_tasks.add_task(target.unlink,True)
    return FileResponse(target,filename=Path(path).name,media_type="application/octet-stream")
@router.post("/transfer")
def transfer(payload:dict,db:Session=Depends(get_db)):return call(S.transfer,db,str(payload.get("source_path") or ""),str(payload.get("destination_path") or ""),str(payload.get("operation") or "copy"))
@router.post("/rename")
def rename(payload:dict,db:Session=Depends(get_db)):return call(S.rename,db,str(payload.get("path") or ""),str(payload.get("new_name") or ""))
