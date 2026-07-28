from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from sqlalchemy.orm import Session

from app.services.beam_cli_environment_service import beam_cli_environment_service
from app.services.infrastructure_provider_service import InfrastructureProviderService
from app.services.beam_credentials_service import beam_credentials_service

class BeamFileManagerError(RuntimeError): pass

class BeamFileManagerService:
    @classmethod
    def _env(cls, db: Session):
        cfg = InfrastructureProviderService.get_beam(db)
        try:
            beam_credentials_service.require_token(cfg)
        except Exception as exc:
            raise BeamFileManagerError(str(exc)) from exc
        exe = beam_cli_environment_service.ensure(timeout_seconds=900)
        home = tempfile.mkdtemp(prefix="tryon-beam-file-manager-")
        env = os.environ.copy(); env.update({"HOME": home, "USERPROFILE": home})
        try:
            auth = beam_credentials_service.configure_cli(
                executable=exe, config=cfg, env=env, timeout_seconds=30
            )
        except Exception as exc:
            shutil.rmtree(home, ignore_errors=True)
            raise BeamFileManagerError(str(exc)) from exc
        return cfg, exe, auth.env, home
    @classmethod
    def _run(cls, db, args, timeout=3600):
        cfg, exe, env, home = cls._env(db)
        try:
            done=subprocess.run([exe,*args],env=env,capture_output=True,text=True,timeout=timeout)
            if done.returncode!=0: raise BeamFileManagerError((done.stderr or done.stdout or "Beam CLI terminó con error")[-4000:])
            return cfg, done.stdout or ""
        finally: shutil.rmtree(home,ignore_errors=True)
    @staticmethod
    def _clean(path): return "/".join(p for p in str(path or "").replace("\\","/").split("/") if p not in {"",".",".."})
    @classmethod
    def list_volumes(cls, db):
        cfg,_=cls._run(db,["volume","list"],120)
        return [{"name":cfg.volume_name,"driver":"beam","mountpoint":"/models","scope":"global","labels":{"provider":"beam"},"options":{}}]
    @classmethod
    def list_directory(cls,db,volume,path=""):
        cfg=InfrastructureProviderService.get_beam(db); clean=cls._clean(path); target=f"beam://{cfg.volume_name}"+(f"/{clean}" if clean else "")
        _,out=cls._run(db,["ls",target],300)
        items=[]
        for line in out.splitlines():
            raw=line.strip()
            if not raw or raw.lower().startswith(("name ","total ")): continue
            name=raw.rstrip("/").split()[-1].rstrip("/").split("/")[-1]
            if not name or name in {".",".."}: continue
            is_dir=raw.endswith("/") or raw.lower().startswith(("dir ","directory "))
            child="/".join(x for x in [clean,name] if x)
            items.append({"name":name,"path":child,"type":"directory" if is_dir else "file","size":0,"modified_at":None})
        return {"volume":cfg.volume_name,"path":clean,"items":items}
    @classmethod
    def create_directory(cls,db,volume,path):
        # Beam volumes do not need explicit empty folders; create a marker object.
        with tempfile.TemporaryDirectory(prefix="tryon-beam-mkdir-") as tmp:
            marker=Path(tmp)/".keep"; marker.write_bytes(b"")
            cfg=InfrastructureProviderService.get_beam(db); target=f"beam://{cfg.volume_name}/{cls._clean(path)}/.keep"
            cls._run(db,["cp",str(marker),target],300)
        return {"success":True,"volume":cfg.volume_name,"path":cls._clean(path)}
    @classmethod
    def upload_file(cls,db,volume,path,local_path):
        cfg=InfrastructureProviderService.get_beam(db); target=f"beam://{cfg.volume_name}/{cls._clean(path)}"
        cls._run(db,["cp",str(local_path),target],max(3600,int(cfg.timeout_seconds)))
        return {"success":True,"volume":cfg.volume_name,"path":cls._clean(path),"size":Path(local_path).stat().st_size}
    @classmethod
    def download_to_temp(cls,db,volume,path):
        cfg=InfrastructureProviderService.get_beam(db); tmp=Path(tempfile.mkdtemp(prefix="tryon-beam-download-")); target=tmp/Path(path).name
        cls._run(db,["cp",f"beam://{cfg.volume_name}/{cls._clean(path)}",str(target)],max(3600,int(cfg.timeout_seconds)))
        return target
    @classmethod
    def delete_path(cls,db,volume,path):
        cfg=InfrastructureProviderService.get_beam(db); cls._run(db,["rm","-r",f"beam://{cfg.volume_name}/{cls._clean(path)}"],600)
        return {"success":True,"volume":cfg.volume_name,"path":cls._clean(path)}
    @classmethod
    def transfer(cls,db,source,destination,operation):
        cfg=InfrastructureProviderService.get_beam(db); src=f"beam://{cfg.volume_name}/{cls._clean(source)}"; dst=f"beam://{cfg.volume_name}/{cls._clean(destination)}"
        cls._run(db,["cp","-r",src,dst],max(3600,int(cfg.timeout_seconds)))
        if operation=="move": cls._run(db,["rm","-r",src],600)
        return {"success":True,"operation":operation,"source_path":source,"destination_path":destination}
    @classmethod
    def rename(cls,db,path,new_name):
        clean=cls._clean(path); parent="/".join(clean.split("/")[:-1]); dst="/".join(x for x in [parent,Path(new_name).name] if x)
        return cls.transfer(db,clean,dst,"move")
