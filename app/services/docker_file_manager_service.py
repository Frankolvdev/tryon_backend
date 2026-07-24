from __future__ import annotations
import asyncio, hashlib, json, os, re, secrets, subprocess, tempfile, uuid
from urllib.parse import quote
from pathlib import Path, PurePosixPath
from typing import Any, AsyncIterator, BinaryIO

import httpx

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
        cls._remove_upload_worker(safe_name)
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

    WORKER_IMAGE = os.getenv(
        "DOCKER_FILE_MANAGER_UPLOAD_WORKER_IMAGE",
        "tryon/docker-volume-upload-worker:1.0",
    )
    WORKER_INTERNAL_PORT = 8765

    @classmethod
    def _worker_name(cls, volume: str) -> str:
        digest = hashlib.sha256(volume.encode("utf-8")).hexdigest()[:16]
        return f"tryon-volume-upload-{digest}"

    @classmethod
    def _worker_source_dir(cls) -> Path:
        return Path(__file__).resolve().parents[2] / "docker" / "docker-volume-upload-worker"

    @classmethod
    def _ensure_worker_image(cls) -> None:
        inspected = subprocess.run(
            ["docker", "image", "inspect", cls.WORKER_IMAGE],
            capture_output=True,
            check=False,
        )
        if inspected.returncode == 0:
            return
        source_dir = cls._worker_source_dir()
        dockerfile = source_dir / "Dockerfile"
        if not dockerfile.is_file():
            raise DockerFileManagerError(
                f"Upload worker Dockerfile not found: {dockerfile}"
            )
        cls._run(
            ["build", "-t", cls.WORKER_IMAGE, "-f", str(dockerfile), str(source_dir)],
            timeout=1800,
        )

    @classmethod
    def _remove_upload_worker(cls, volume: str) -> None:
        subprocess.run(
            ["docker", "rm", "-f", cls._worker_name(volume)],
            capture_output=True,
            check=False,
        )

    @classmethod
    def _ensure_upload_worker(cls, volume: str) -> tuple[str, str]:
        safe_volume = cls._require_volume(volume)
        cls._ensure_worker_image()
        worker_name = cls._worker_name(safe_volume)

        inspect = subprocess.run(
            ["docker", "inspect", worker_name],
            capture_output=True,
            check=False,
        )
        token = ""
        if inspect.returncode == 0:
            data = json.loads(inspect.stdout.decode("utf-8"))[0]
            mounts = data.get("Mounts") or []
            mounted_volume = next(
                (m.get("Name") for m in mounts if m.get("Destination") == "/data"),
                None,
            )
            if mounted_volume != safe_volume:
                cls._remove_upload_worker(safe_volume)
                inspect = subprocess.CompletedProcess([], 1, b"", b"")
            else:
                env = data.get("Config", {}).get("Env") or []
                token = next(
                    (item.split("=", 1)[1] for item in env if item.startswith("UPLOAD_TOKEN=")),
                    "",
                )
                if not data.get("State", {}).get("Running"):
                    cls._run(["start", worker_name])

        if inspect.returncode != 0:
            token = secrets.token_urlsafe(32)
            cls._run(
                [
                    "run", "-d",
                    "--name", worker_name,
                    "--restart", "unless-stopped",
                    "-e", f"UPLOAD_TOKEN={token}",
                    "-v", f"{safe_volume}:/data",
                    "-p", f"127.0.0.1::{cls.WORKER_INTERNAL_PORT}",
                    cls.WORKER_IMAGE,
                ],
                timeout=120,
            )

        port_result = cls._run(
            ["port", worker_name, f"{cls.WORKER_INTERNAL_PORT}/tcp"],
            timeout=30,
        )
        mapping = port_result.stdout.decode("utf-8", "replace").strip().splitlines()[0]
        host_port = mapping.rsplit(":", 1)[-1]
        if not host_port.isdigit():
            raise DockerFileManagerError("Could not resolve upload worker port")
        return f"http://127.0.0.1:{host_port}", token

    @classmethod
    async def upload_async_stream(
        cls,
        volume: str,
        path: str,
        chunks: AsyncIterator[bytes],
        overwrite: bool = False,
        content_length: int | None = None,
    ) -> dict[str, Any]:
        """Stream once, directly into a container with the target volume mounted.

        The browser upload and the Docker-volume write happen simultaneously. No
        Windows temporary file, ``docker cp`` or second full-file pass is used.
        """
        destination = cls._path(path, False)
        base_url, token = await asyncio.to_thread(cls._ensure_upload_worker, volume)

        async def body() -> AsyncIterator[bytes]:
            async for chunk in chunks:
                if chunk:
                    yield chunk

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/octet-stream",
        }
        if content_length is not None and content_length >= 0:
            headers["Content-Length"] = str(content_length)

        url = (
            f"{base_url}/upload?path={quote(destination, safe='/')}"
            f"&overwrite={'true' if overwrite else 'false'}"
        )
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                response = await client.post(url, headers=headers, content=body())
        except httpx.HTTPError as exc:
            raise DockerFileManagerError(f"Upload worker connection failed: {exc}") from exc

        if response.status_code >= 400:
            try:
                detail = response.json().get("detail")
            except Exception:
                detail = response.text
            raise DockerFileManagerError(detail or "Upload worker rejected the file")

        result = response.json()
        return {
            "success": True,
            "path": destination,
            "size": int(result.get("size") or content_length or 0),
            "method": "direct-volume-worker",
        }

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
