from __future__ import annotations
import asyncio, json, os, re, subprocess, tempfile, uuid
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO

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
    def volume_exists(cls, name: str) -> bool:
        safe_name = cls._volume(name)
        result = subprocess.run(
            ["docker", "volume", "inspect", safe_name],
            capture_output=True,
            check=False,
        )
        return result.returncode == 0

    @classmethod
    def _require_volume(cls, name: str) -> str:
        safe_name = cls._volume(name)
        if not cls.volume_exists(safe_name):
            raise DockerFileManagerError(f"Docker volume '{safe_name}' does not exist")
        return safe_name

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
        safe_name = cls._require_volume(name)
        args=["volume","rm"] + (["--force"] if force else []) + [safe_name]
        cls._run(args)
        if cls.volume_exists(safe_name):
            raise DockerFileManagerError(f"Docker volume '{safe_name}' could not be removed")
        return {"success":True,"name":safe_name,"deleted":True}
    @classmethod
    def _helper(cls, volume:str, command:str, *, second_volume:str|None=None, input_bytes:bytes|None=None, timeout:int=120)->subprocess.CompletedProcess:
        source_volume = cls._require_volume(volume)
        args=["run","--rm","-i","-v",f"{source_volume}:/data"]
        if second_volume:
            destination_volume = cls._require_volume(second_volume)
            args += ["-v",f"{destination_volume}:/dest"]
        args += [cls.HELPER_IMAGE,"sh","-lc",command]
        return cls._run(args,input_bytes=input_bytes,timeout=timeout)
    @classmethod
    def list_directory(cls,volume:str,path:str="")->dict[str,Any]:
        safe_volume = cls._require_volume(volume)
        p=cls._path(path); target=f"/data/{p}" if p else "/data"
        # Alpine uses BusyBox; its `find` does not support GNU `-printf`.
        script = r"""
set -eu
target="$1"
test -d "$target" || exit 44
find "$target" -mindepth 1 -maxdepth 1 -exec sh -c '
  for entry do
    printf "%s\t%s\t%s\t%s\n" \
      "$entry" \
      "$(stat -c %F "$entry")" \
      "$(stat -c %s "$entry")" \
      "$(stat -c %Y "$entry")"
  done
' sh {} +
"""
        out = cls._run([
            "run", "--rm", "-v", f"{safe_volume}:/data",
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
    async def upload_async_stream(
        cls,
        volume: str,
        path: str,
        chunks,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        """Spool quickly, then use Docker's native copy implementation.

        Directly piping every HTTP chunk to ``docker run -i`` can become
        extremely slow on Windows/Docker Desktop because of subprocess-pipe
        backpressure. ``docker cp`` is much faster and more stable for large
        model files.
        """
        p = cls._path(path, False)
        safe_volume = cls._require_volume(volume)
        helper_name = f"tryon-volume-upload-{uuid.uuid4().hex[:12]}"
        temporary_path: str | None = None
        written = 0

        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix="tryon-volume-upload-",
                suffix=".part",
                delete=False,
                buffering=16 * 1024 * 1024,
            ) as temporary_file:
                temporary_path = temporary_file.name
                async for chunk in chunks:
                    if not chunk:
                        continue
                    temporary_file.write(chunk)
                    written += len(chunk)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())

            await asyncio.to_thread(
                cls._run,
                [
                    "run", "-d", "--name", helper_name,
                    "-v", f"{safe_volume}:/data",
                    cls.HELPER_IMAGE, "sleep", "21600",
                ],
                timeout=120,
            )

            final_target = f"/data/{p}"
            staging_target = f"{final_target}.uploading-{uuid.uuid4().hex[:8]}"
            prepare_script = """set -eu
final="$1"
overwrite="$2"
mkdir -p -- "$(dirname "$final")"
if [ "$overwrite" != "true" ] && [ -e "$final" ]; then
  echo "Destination already exists" >&2
  exit 17
fi
"""
            await asyncio.to_thread(
                cls._run,
                [
                    "exec", helper_name, "sh", "-lc", prepare_script,
                    "sh", final_target, "true" if overwrite else "false",
                ],
                timeout=120,
            )

            await asyncio.to_thread(
                cls._run,
                ["cp", temporary_path, f"{helper_name}:{staging_target}"],
                timeout=21600,
            )

            commit_script = """set -eu
staging="$1"
final="$2"
overwrite="$3"
if [ "$overwrite" = "true" ]; then
  mv -f -- "$staging" "$final"
else
  test ! -e "$final"
  mv -- "$staging" "$final"
fi
"""
            await asyncio.to_thread(
                cls._run,
                [
                    "exec", helper_name, "sh", "-lc", commit_script,
                    "sh", staging_target, final_target,
                    "true" if overwrite else "false",
                ],
                timeout=120,
            )
            return {"success": True, "path": p, "size": written}
        finally:
            subprocess.run(
                ["docker", "rm", "-f", helper_name],
                capture_output=True,
                check=False,
            )
            if temporary_path:
                try:
                    os.remove(temporary_path)
                except FileNotFoundError:
                    pass

    @classmethod
    def upload_stream(
        cls,
        volume: str,
        path: str,
        stream: BinaryIO,
        overwrite: bool = False,
        chunk_size: int = 8 * 1024 * 1024,
    ) -> dict[str, Any]:
        p = cls._path(path, False)
        safe_volume = cls._require_volume(volume)
        guard = "" if overwrite else f"test ! -e '/data/{p}' && "
        command = f"mkdir -p -- \"$(dirname '/data/{p}')\"; {guard}cat > '/data/{p}'"
        args = [
            "docker", "run", "--rm", "-i",
            "-v", f"{safe_volume}:/data",
            cls.HELPER_IMAGE, "sh", "-lc", command,
        ]
        process = subprocess.Popen(
            args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        written = 0
        try:
            if process.stdin is None:
                raise DockerFileManagerError("Docker upload stream could not be opened")
            while True:
                chunk = stream.read(chunk_size)
                if not chunk:
                    break
                process.stdin.write(chunk)
                written += len(chunk)
            process.stdin.close()
            stdout = process.stdout.read() if process.stdout else b""
            stderr = process.stderr.read() if process.stderr else b""
            return_code = process.wait(timeout=3600)
        except Exception:
            process.kill()
            process.wait()
            raise
        if return_code != 0:
            message = stderr.decode("utf-8", "replace").strip() or stdout.decode("utf-8", "replace").strip()
            raise DockerFileManagerError(message or "Docker upload failed")
        return {"success": True, "path": p, "size": written}

    @classmethod
    def upload_bytes(cls,volume:str,path:str,data:bytes,overwrite:bool=False):
        from io import BytesIO
        return cls.upload_stream(volume, path, BytesIO(data), overwrite)
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
