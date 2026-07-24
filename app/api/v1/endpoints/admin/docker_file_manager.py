from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from app.api.v1.guards.admin_guard import admin_guard
from app.schemas.docker_file_manager import *
from app.services.docker_file_manager_service import DockerFileManagerError, DockerFileManagerService as S
router=APIRouter(prefix="/docker-file-manager",dependencies=[Depends(admin_guard)])
def call(fn,*a,**kw):
    try:return fn(*a,**kw)
    except DockerFileManagerError as exc: raise HTTPException(status_code=400,detail=str(exc)) from exc
@router.get("/volumes")
def volumes(): return {"items":call(S.list_volumes)}
@router.post("/volumes")
def create(p: DockerVolumeCreate): return call(S.create_volume,p.name,p.driver,p.labels)
@router.get("/volumes/{name}")
def inspect(name:str): return call(S.inspect_volume,name)
@router.delete("/volumes/{name}")
def remove(name:str,force:bool=False): return call(S.delete_volume,name,force)
@router.get("/browse")
def browse(volume:str=Query(...),path:str=""): return call(S.list_directory,volume,path)
@router.post("/directories")
def mkdir(p:DockerDirectoryCreate): return call(S.create_directory,p.volume,p.path,p.parents)
@router.delete("/paths")
def delete(volume:str,path:str): return call(S.delete_path,volume,path)
@router.post("/rename")
def rename(p:DockerRenamePayload): return call(S.rename,p.volume,p.path,p.new_name)
@router.post("/transfer")
def transfer(p:DockerTransferPayload): return call(S.transfer,p.source_volume,p.source_path,p.destination_volume,p.destination_path,p.operation,p.overwrite)
@router.post("/upload")
def upload(volume:str=Form(...),path:str=Form(...),overwrite:bool=Form(False),file:UploadFile=File(...)):
    try:
        file.file.seek(0)
        return call(S.upload_stream, volume, path, file.file, overwrite)
    finally:
        file.file.close()
@router.get("/download")
def download(volume:str,path:str):
    data=call(S.download_bytes,volume,path); name=path.replace('\\','/').split('/')[-1]
    return Response(data,media_type="application/octet-stream",headers={"Content-Disposition":f'attachment; filename="{name}"'})
@router.post("/preview")
def preview(p:DockerCommandPreview): return S.preview(p.operation,p.parameters)
