from __future__ import annotations
import json, os, re, subprocess, tempfile
from pathlib import Path, PurePosixPath
from typing import Any

class DockerFileManagerError(RuntimeError): pass

class DockerFileManagerService:
    HELPER_IMAGE = os.getenv("DOCKER_FILE_MANAGER_IMAGE", "alpine:3.20")
    @classmethod
    def _run(cls, args:list[str], *, input_bytes:bytes|None=None, timeout:int=120) -> subprocess.CompletedProcess:
        try:
            result=subprocess.run(["docker",*args],input=input_bytes,capture_output=True,timeout=timeout,check=False)
        except (OSError, subprocess.TimeoutExpired) as exc: raise DockerFileManagerError(str(exc)) from exc
        if result.returncode != 0: raise DockerFileManagerError(result.stderr.decode("utf-8","replace").strip() or "Docker command failed")
        return result
    @staticmethod
    def _volume(name:str)->str:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]+",name): raise DockerFileManagerError("Invalid Docker volume name")
        return name
    @staticmethod
    def _path(value:str, allow_root:bool=True)->str:
        raw=(value or "").replace("\\","/").strip("/")
        p=PurePosixPath(raw)
        if any(part in ("..","") for part in p.parts):
            if raw: raise DockerFileManagerError("Invalid path")
        normalized=str(p) if raw else ""
        if not allow_root and not normalized: raise DockerFileManagerError("Root path is not allowed")
        return normalized
    @classmethod
    def list_volumes(cls)->list[dict[str,Any]]:
        names=cls._run(["volume","ls","--format","{{.Name}}"]).stdout.decode().splitlines()
        return [cls.inspect_volume(n) for n in names if n.strip()]
    @classmethod
    def inspect_volume(cls,name:str)->dict[str,Any]:
        data=json.loads(cls._run(["volume","inspect",cls._volume(name)]).stdout.decode())[0]
        return {"name":data.get("Name"),"driver":data.get("Driver"),"mountpoint":data.get("Mountpoint"),"scope":data.get("Scope"),"labels":data.get("Labels") or {},"options":data.get("Options") or {},"created_at":data.get("CreatedAt")}
    @classmethod
    def create_volume(cls,name:str,driver:str="local",labels:dict[str,str]|None=None)->dict[str,Any]:
        args=["volume","create","--driver",driver]
        for k,v in (labels or {}).items(): args += ["--label",f"{k}={v}"]
        args.append(cls._volume(name)); cls._run(args); return cls.inspect_volume(name)
    @classmethod
    def delete_volume(cls,name:str,force:bool=False)->dict[str,Any]:
        args=["volume","rm"] + (["--force"] if force else []) + [cls._volume(name)]
        cls._run(args); return {"success":True,"name":name}
    @classmethod
    def _helper(cls, volume:str, command:str, *, second_volume:str|None=None, input_bytes:bytes|None=None, timeout:int=120)->subprocess.CompletedProcess:
        args=["run","--rm","-i","-v",f"{cls._volume(volume)}:/data"]
        if second_volume: args += ["-v",f"{cls._volume(second_volume)}:/dest"]
        args += [cls.HELPER_IMAGE,"sh","-lc",command]
        return cls._run(args,input_bytes=input_bytes,timeout=timeout)
    @classmethod
    def list_directory(cls,volume:str,path:str="")->dict[str,Any]:
        p=cls._path(path); target=f"/data/{p}" if p else "/data"
        # Alpine uses BusyBox; its `find` does not support GNU `-printf`.
        script = r"""
set -eu
target="$1"
test -d "$target" || exit 44
find "$target" -mindepth 1 -maxdepth 1 -exec stat -c '%n\t%F\t%s\t%Y' {} \;
"""
        out = cls._run([
            "run", "--rm", "-v", f"{cls._volume(volume)}:/data",
            cls.HELPER_IMAGE, "sh", "-lc", script, "sh", target,
        ])
        items=[]
        prefix = target.rstrip("/") + "/"
        for line in out.stdout.decode("utf-8","replace").splitlines():
            full_name,kind,size,modified=(line.split("\t",3)+["","",""])[:4]
            name = full_name[len(prefix):] if full_name.startswith(prefix) else PurePosixPath(full_name).name
            rel=f"{p}/{name}" if p else name
            entry_type = "directory" if "directory" in kind.lower() else "file"
            items.append({"name":name,"path":rel,"type":entry_type,"size":int(size or 0),"modified_at":modified})
        items.sort(key=lambda item: (item["type"] != "directory", item["name"].lower()))
        return {"volume":volume,"path":p,"items":items}
    @classmethod
    def create_directory(cls,volume:str,path:str,parents:bool=True):
        p=cls._path(path,False); flag="-p" if parents else ""; cls._helper(volume,f"mkdir {flag} -- '/data/{p}'"); return {"success":True,"path":p}
    @classmethod
    def delete_path(cls,volume:str,path:str):
        p=cls._path(path,False); cls._helper(volume,f"rm -rf -- '/data/{p}'"); return {"success":True,"path":p}
    @classmethod
    def rename(cls,volume:str,path:str,new_name:str):
        p=PurePosixPath(cls._path(path,False)); safe=cls._path(new_name,False)
        if "/" in safe: raise DockerFileManagerError("new_name must not contain folders")
        dest=str(p.parent/safe) if str(p.parent)!="." else safe
        cls._helper(volume,f"test ! -e '/data/{dest}' && mv -- '/data/{p}' '/data/{dest}'")
        return {"success":True,"path":dest}
    @classmethod
    def upload_bytes(cls,volume:str,path:str,data:bytes,overwrite:bool=False):
        p=cls._path(path,False); guard="" if overwrite else f"test ! -e '/data/{p}' && "
        cls._helper(volume,f"mkdir -p -- \"$(dirname '/data/{p}')\"; {guard}cat > '/data/{p}'",input_bytes=data,timeout=600)
        return {"success":True,"path":p,"size":len(data)}
    @classmethod
    def download_bytes(cls,volume:str,path:str)->bytes:
        p=cls._path(path,False); return cls._helper(volume,f"test -f '/data/{p}' && cat '/data/{p}'",timeout=600).stdout
    @classmethod
    def transfer(cls,sv:str,sp:str,dv:str,dp:str,operation:str="copy",overwrite:bool=False):
        sp=cls._path(sp,False); dp=cls._path(dp,False); guard="" if overwrite else f"test ! -e '/dest/{dp}' && "
        cmd=f"mkdir -p -- \"$(dirname '/dest/{dp}')\"; {guard}cp -a -- '/data/{sp}' '/dest/{dp}'"
        cls._helper(sv,cmd,second_volume=dv,timeout=600)
        if operation=="move": cls.delete_path(sv,sp)
        return {"success":True,"operation":operation,"destination_path":dp}
    @classmethod
    def copy_local_tree_to_volume(cls,source:Path,volume:str,destination_path:str,overwrite:bool)->None:
        dest=cls._path(destination_path)
        with tempfile.NamedTemporaryFile(suffix=".tar") as temp:
            cls._run(["run","--rm","-v",f"{source.resolve()}:/source:ro","-v",f"{cls._volume(volume)}:/data",cls.HELPER_IMAGE,"sh","-lc",f"mkdir -p '/data/{dest}'; {'rm -rf /data/'+dest+'/*;' if overwrite and dest else ''} cp -a /source/. '/data/{dest}/'"],timeout=3600)
    @classmethod
    def preview(cls,operation:str,params:dict[str,Any])->dict[str,Any]:
        return {"operation":operation,"command":f"docker run --rm -v <volume>:/data {cls.HELPER_IMAGE} sh -lc <safe-{operation}-command>","parameters":params,"note":"Vista sanitizada; las rutas reales se validan antes de ejecutar."}
