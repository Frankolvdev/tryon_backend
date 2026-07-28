from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import BinaryIO

import boto3
from botocore.config import Config
from sqlalchemy.orm import Session

from app.services.infrastructure_provider_service import InfrastructureProviderService


class RunPodFileManagerError(RuntimeError):
    pass


class RunPodFileManagerService:
    @classmethod
    def _client(cls, db: Session):
        cfg = InfrastructureProviderService.get_runpod(db)
        if not cfg.s3_access_key or not cfg.s3_secret_key:
            raise RunPodFileManagerError("Configura Access Key y Secret de la S3 API de RunPod.")
        if not cfg.network_volume_id:
            raise RunPodFileManagerError("Configura el Network Volume ID de RunPod.")
        if not cfg.data_center_id:
            raise RunPodFileManagerError("Configura el Data Center ID de RunPod.")
        dc_raw = str(cfg.data_center_id).strip()
        dc = dc_raw.lower()
        endpoint = f"https://s3api-{dc}.runpod.io/"
        client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            region_name=dc_raw.upper(),
            aws_access_key_id=cfg.s3_access_key,
            aws_secret_access_key=cfg.s3_secret_key,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                retries={"max_attempts": 12, "mode": "standard"},
                connect_timeout=60,
                read_timeout=900,
            ),
        )
        return cfg, client, str(cfg.network_volume_id)

    @staticmethod
    def _clean(path: str) -> str:
        return "/".join(part for part in str(path or "").replace("\\", "/").split("/") if part not in {"", ".", ".."})

    @classmethod
    def list_volumes(cls, db: Session):
        cfg, client, bucket = cls._client(db)
        client.head_bucket(Bucket=bucket)
        return [{"name": bucket, "driver": "runpod-s3", "mountpoint": "/workspace", "scope": "global", "labels": {"provider": "runpod", "display_name": cfg.network_volume_name}, "options": {"data_center_id": cfg.data_center_id}}]

    @classmethod
    def list_directory(cls, db: Session, volume: str, path: str = ""):
        _, client, bucket = cls._client(db)
        clean = cls._clean(path)
        prefix = f"{clean}/" if clean else ""
        # RunPod's S3 layer can return transient 502 responses when listing a
        # large volume. Keep the root browse bounded and let botocore retry the
        # request instead of opening an unbounded paginator.
        page = client.list_objects_v2(
            Bucket=bucket,
            Prefix=prefix,
            Delimiter="/",
            MaxKeys=1000,
        )
        items = {}
        for row in page.get("CommonPrefixes", []):
            key = str(row.get("Prefix") or "").rstrip("/")
            name = key.split("/")[-1]
            if name and name != ".s3compat_uploads":
                items[key] = {"name": name, "path": key, "type": "directory", "size": 0, "modified_at": None}
        for row in page.get("Contents", []):
            key = str(row.get("Key") or "")
            if not key or key == prefix or key.startswith(".s3compat_uploads/"):
                continue
            relative = key[len(prefix):]
            if "/" in relative:
                continue
            items[key] = {"name": relative, "path": key, "type": "directory" if key.endswith("/") else "file", "size": int(row.get("Size") or 0), "modified_at": row.get("LastModified").isoformat() if row.get("LastModified") else None}
        return {
            "volume": bucket,
            "path": clean,
            "items": sorted(items.values(), key=lambda x: (x["type"] != "directory", x["name"].lower())),
            "truncated": bool(page.get("IsTruncated")),
        }

    @classmethod
    def create_directory(cls, db: Session, volume: str, path: str):
        _, client, bucket = cls._client(db)
        key = cls._clean(path).rstrip("/") + "/"
        client.put_object(Bucket=bucket, Key=key, Body=b"")
        return {"success": True, "volume": bucket, "path": key.rstrip("/")}

    @classmethod
    def upload_file(cls, db: Session, volume: str, path: str, fileobj: BinaryIO, size: int | None = None):
        _, client, bucket = cls._client(db)
        key = cls._clean(path)
        if not key:
            raise RunPodFileManagerError("La ruta de destino está vacía.")
        client.upload_fileobj(fileobj, bucket, key, Config=boto3.s3.transfer.TransferConfig(multipart_threshold=64*1024*1024, multipart_chunksize=64*1024*1024, max_concurrency=4, use_threads=True))
        return {"success": True, "volume": bucket, "path": key, "size": size or 0}

    @classmethod
    def download_to_temp(cls, db: Session, volume: str, path: str) -> Path:
        _, client, bucket = cls._client(db)
        key = cls._clean(path)
        fd, name = tempfile.mkstemp(prefix="tryon-runpod-download-", suffix="-" + Path(key).name)
        os.close(fd)
        target = Path(name)
        try:
            client.download_file(bucket, key, str(target))
            return target
        except Exception:
            target.unlink(missing_ok=True)
            raise

    @classmethod
    def delete_path(cls, db: Session, volume: str, path: str):
        _, client, bucket = cls._client(db)
        key = cls._clean(path)
        prefix = key.rstrip("/") + "/"
        keys = [key]
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            keys.extend(str(o["Key"]) for o in page.get("Contents", []))
        for i in range(0, len(keys), 1000):
            batch = [{"Key": k} for k in dict.fromkeys(keys[i:i+1000]) if k]
            if batch:
                client.delete_objects(Bucket=bucket, Delete={"Objects": batch, "Quiet": True})
        return {"success": True, "volume": bucket, "path": key}

    @classmethod
    def transfer(cls, db: Session, source_path: str, destination_path: str, operation: str):
        _, client, bucket = cls._client(db)
        source, destination = cls._clean(source_path), cls._clean(destination_path)
        if not source or not destination:
            raise RunPodFileManagerError("Origen y destino son obligatorios.")
        response = client.list_objects_v2(Bucket=bucket, Prefix=source.rstrip("/") + "/", MaxKeys=1)
        is_dir = bool(response.get("Contents"))
        sources = []
        if is_dir:
            paginator = client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=bucket, Prefix=source.rstrip("/") + "/"):
                sources.extend(str(o["Key"]) for o in page.get("Contents", []))
        else:
            sources = [source]
        for key in sources:
            suffix = key[len(source):].lstrip("/") if is_dir else ""
            dest_key = "/".join(x for x in [destination.rstrip("/"), suffix] if x)
            client.copy_object(Bucket=bucket, CopySource={"Bucket": bucket, "Key": key}, Key=dest_key)
        if operation == "move":
            cls.delete_path(db, bucket, source)
        return {"success": True, "operation": operation, "source_path": source, "destination_path": destination}

    @classmethod
    def rename(cls, db: Session, path: str, new_name: str):
        source = cls._clean(path)
        parent = "/".join(source.split("/")[:-1])
        destination = "/".join(x for x in [parent, Path(new_name).name] if x)
        return cls.transfer(db, source, destination, "move")
