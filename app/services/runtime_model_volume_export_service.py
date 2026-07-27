from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.models.runtime_builder_config import RuntimeBuilderConfig
from app.services.runtime_context_generator_service import RuntimeContextGeneratorService
from app.services.docker_file_manager_service import DockerFileManagerService
from app.services.modal_file_manager_service import ModalFileManagerService

ProgressCallback = Callable[[str, int, str], None]


class RuntimeModelVolumeExportService:
    """Exports only workflow-required models using ComfyUI's models layout."""

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _resolve(config: RuntimeBuilderConfig, comfyui_path: str) -> tuple[Path, list[dict[str, Any]]]:
        comfy = RuntimeContextGeneratorService._find_comfyui(comfyui_path)
        records: list[dict[str, Any]] = []
        for item in [m for m in (config.models or []) if m.get("enabled", True)]:
            source = RuntimeContextGeneratorService._find_model(comfy, item)
            record = dict(item)
            if source is None:
                record.update({"found": False, "source_path": None, "relative_path": None, "size_bytes": 0})
            else:
                relative = source.relative_to(comfy / "models")
                record.update({
                    "found": True,
                    "source_path": str(source),
                    "relative_path": f"models/{relative.as_posix()}",
                    "size_bytes": source.stat().st_size,
                })
            records.append(record)
        return comfy, records

    @staticmethod
    def analyze(config: RuntimeBuilderConfig, comfyui_path: str) -> dict[str, Any]:
        comfy, records = RuntimeModelVolumeExportService._resolve(config, comfyui_path)
        found = [item for item in records if item["found"]]
        missing = [item for item in records if not item["found"]]
        return {
            "source_comfyui": str(comfy),
            "models_detected": len(records),
            "models_found": len(found),
            "models_missing": len(missing),
            "bytes_total": sum(int(item["size_bytes"]) for item in found),
            "items": records,
        }


    @staticmethod
    def _copy_to_runpod(session: Any, models_root: Path, remote_path: str, overwrite: bool, notify: ProgressCallback) -> dict[str, Any]:
        from boto3 import client as boto3_client
        from boto3.s3.transfer import TransferConfig
        from botocore.config import Config
        from botocore.exceptions import ClientError
        from app.services.infrastructure_provider_service import InfrastructureProviderService

        cfg = InfrastructureProviderService.get_runpod(session)
        volume_id = str(cfg.network_volume_id or "").strip()
        data_center = str(cfg.data_center_id or "").strip().upper()
        access_key = str(cfg.s3_access_key or "").strip()
        secret_key = str(cfg.s3_secret_key or "").strip()
        missing = [name for name, value in (("Network Volume ID", volume_id), ("Data Center ID", data_center), ("S3 Access Key", access_key), ("S3 Secret Key", secret_key)) if not value]
        if missing:
            raise ValueError("Configura RunPod antes de exportar: " + ", ".join(missing) + ".")
        endpoint = f"https://s3api-{data_center.lower()}.runpod.io/"
        s3 = boto3_client(
            "s3",
            endpoint_url=endpoint,
            region_name=data_center,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(retries={"max_attempts": 10, "mode": "standard"}, s3={"addressing_style": "path"}),
        )
        files = [item for item in models_root.rglob("*") if item.is_file()]
        transfer = TransferConfig(multipart_threshold=256 * 1024 * 1024, multipart_chunksize=64 * 1024 * 1024, max_concurrency=4, use_threads=True)
        uploaded = skipped = 0
        for index, source in enumerate(files, start=1):
            relative = source.relative_to(models_root).as_posix()
            key = "/".join(part for part in (remote_path.strip("/"), relative) if part)
            if not overwrite:
                try:
                    remote = s3.head_object(Bucket=volume_id, Key=key)
                    if int(remote.get("ContentLength") or -1) == source.stat().st_size:
                        skipped += 1
                        continue
                except ClientError as exc:
                    status = int(exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode") or 0)
                    code = str(exc.response.get("Error", {}).get("Code") or "")
                    if status not in {403, 404} and code not in {"404", "NoSuchKey", "NotFound"}:
                        raise
            notify("runpod-copy", 94 + min(4, int(4 * index / max(1, len(files)))), f"Subiendo {index} de {len(files)} archivos a RunPod…")
            s3.upload_file(str(source), volume_id, key, Config=transfer)
            uploaded += 1
        return {"volume_id": volume_id, "data_center_id": data_center, "endpoint": endpoint, "path": remote_path, "files_uploaded": uploaded, "files_skipped": skipped}

    @staticmethod
    def _copy_to_beam(session: Any, models_root: Path, remote_path: str, overwrite: bool, notify: ProgressCallback) -> dict[str, Any]:
        from app.services.infrastructure_provider_service import InfrastructureProviderService
        from app.services.beam_cli_environment_service import beam_cli_environment_service

        cfg = InfrastructureProviderService.get_beam(session)
        if not cfg.api_key:
            raise ValueError("Configura la API key de Beam antes de exportar.")
        volume_name = str(cfg.volume_name or "").strip()
        if not volume_name:
            raise ValueError("Configura el nombre del volumen Beam antes de exportar.")
        executable = beam_cli_environment_service.ensure(timeout_seconds=900)
        import tempfile
        env = os.environ.copy()
        home = tempfile.mkdtemp(prefix="tryon-beam-export-")
        env.update({"HOME": home, "USERPROFILE": home})
        configured = subprocess.run([executable, "configure", "default", "--token", cfg.api_key], env=env, capture_output=True, text=True, timeout=30)
        if configured.returncode != 0:
            output = "\n".join(part for part in (configured.stdout, configured.stderr) if part).strip()
            raise RuntimeError(f"Beam CLI rechazó la API key: {output[-3000:]}")
        target = f"beam://{volume_name}" + (f"/{remote_path.strip('/')}" if remote_path.strip('/') else "")
        notify("beam-copy", 94, f"Subiendo modelos al volumen Beam {volume_name}…")
        command = [executable, "cp", str(models_root), target]
        completed = subprocess.run(command, env=env, capture_output=True, text=True, timeout=max(900, int(cfg.timeout_seconds)))
        output = "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()
        if completed.returncode != 0:
            raise RuntimeError(f"Beam CLI no pudo copiar los modelos: {output[-4000:]}")
        return {"volume_name": volume_name, "path": remote_path, "target": target, "overwrite_requested": overwrite, "output": output[-4000:]}

    @staticmethod
    def export(
        config: RuntimeBuilderConfig,
        payload: Any,
        progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        notify = progress or (lambda _phase, _percent, _message: None)
        notify("analyzing", 2, "Localizando los modelos requeridos…")
        comfy, records = RuntimeModelVolumeExportService._resolve(config, payload.comfyui_path)

        base = (
            Path(payload.output_directory).expanduser().resolve()
            if payload.output_directory
            else (
                Path(config.export_root_directory).expanduser().resolve()
                if config.export_root_directory
                else Path(os.getenv("RUNTIME_EXPORTS_DIR", "runtime_exports")).resolve()
            )
        )
        output = base / f"{RuntimeContextGeneratorService._safe(config.project_key or config.name)}-models-volume"
        models_root = output / "models"
        output.mkdir(parents=True, exist_ok=True)
        models_root.mkdir(parents=True, exist_ok=True)

        copied = 0
        overwritten = 0
        skipped = 0
        missing = 0
        bytes_copied = 0
        warnings: list[str] = []
        manifest_items: list[dict[str, Any]] = []
        total = max(1, len(records))
        sam3_tree_processed = False

        for index, item in enumerate(records):
            record = dict(item)
            if not item["found"]:
                missing += 1
                record["status"] = "missing"
                warnings.append(f"Modelo no localizado: {item.get('target_path') or item.get('name')}")
                manifest_items.append(record)
                continue

            source = Path(str(item["source_path"]))
            relative = source.relative_to(comfy / "models")
            destination = models_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)

            # SAM3 es una categoría compuesta: el loader TBG requiere todos los
            # archivos y subdirectorios de models/sam3. Las demás categorías
            # continúan exportándose modelo por modelo.
            if relative.parts and relative.parts[0].lower() == "sam3" and not sam3_tree_processed:
                sam3_source = comfy / "models" / relative.parts[0]
                sam3_destination = models_root / relative.parts[0]
                for tree_source in [path for path in sam3_source.rglob("*") if path.is_file()]:
                    tree_relative = tree_source.relative_to(sam3_source)
                    tree_destination = sam3_destination / tree_relative
                    tree_destination.parent.mkdir(parents=True, exist_ok=True)
                    tree_copy = True
                    if tree_destination.exists():
                        if payload.skip_identical and tree_destination.stat().st_size == tree_source.stat().st_size:
                            if payload.calculate_sha256:
                                tree_copy = RuntimeModelVolumeExportService._sha256(tree_source) != RuntimeModelVolumeExportService._sha256(tree_destination)
                            else:
                                tree_copy = False
                        elif not payload.overwrite:
                            tree_copy = False
                    if tree_copy:
                        shutil.copy2(tree_source, tree_destination)
                        copied += 1
                        bytes_copied += tree_source.stat().st_size
                    else:
                        skipped += 1
                sam3_tree_processed = True
                record.update({
                    "status": "copied-tree",
                    "sha256": RuntimeModelVolumeExportService._sha256(source) if payload.calculate_sha256 else item.get("sha256"),
                    "destination_path": str(destination),
                    "relative_path": f"models/{relative.as_posix()}",
                    "recursive_category": True,
                })
                manifest_items.append(record)
                notify("copying", 5 + int(88 * (index + 1) / total), f"Procesando modelo {index + 1} de {len(records)}…")
                continue
            elif relative.parts and relative.parts[0].lower() == "sam3" and sam3_tree_processed:
                record.update({
                    "status": "included-by-tree",
                    "sha256": RuntimeModelVolumeExportService._sha256(source) if payload.calculate_sha256 else item.get("sha256"),
                    "destination_path": str(destination),
                    "relative_path": f"models/{relative.as_posix()}",
                    "recursive_category": True,
                })
                manifest_items.append(record)
                continue

            source_hash: str | None = None
            should_copy = True
            if destination.exists():
                if payload.skip_identical and destination.stat().st_size == source.stat().st_size:
                    if payload.calculate_sha256:
                        source_hash = RuntimeModelVolumeExportService._sha256(source)
                        destination_hash = RuntimeModelVolumeExportService._sha256(destination)
                        should_copy = source_hash != destination_hash
                    else:
                        should_copy = False
                elif not payload.overwrite:
                    should_copy = False

            if should_copy:
                existed_before = destination.exists()
                shutil.copy2(source, destination)
                copied += 1
                if existed_before:
                    overwritten += 1
                bytes_copied += source.stat().st_size
                status = "copied"
            else:
                skipped += 1
                status = "skipped"

            if payload.calculate_sha256 and source_hash is None:
                source_hash = RuntimeModelVolumeExportService._sha256(source)

            record.update({
                "status": status,
                "sha256": source_hash or item.get("sha256"),
                "destination_path": str(destination),
                "relative_path": f"models/{relative.as_posix()}",
            })
            manifest_items.append(record)
            notify(
                "copying",
                5 + int(88 * (index + 1) / total),
                f"Procesando modelo {index + 1} de {len(records)}…",
            )

        destination_type = getattr(payload, "destination_type", "local")
        docker_volume = getattr(payload, "docker_volume", None)
        docker_path = (getattr(payload, "docker_path", "") or "").strip("/\\")

        manifest = {
            "contract": "tryon.models-volume/v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "project_key": config.project_key,
            "runtime_version": config.runtime_version,
            "source_comfyui": str(comfy),
            "volume_mount_path": "/models",
            "models": manifest_items,
            "summary": {
                "models_detected": len(records),
                "models_found": len(records) - missing,
                "models_missing": missing,
                "models_copied": copied,
                "models_skipped": skipped,
                "models_overwritten": overwritten,
                "errors": 0,
                "elapsed_seconds": round(time.perf_counter() - started, 3),
                "destination": destination_type,
                "bytes_copied": bytes_copied,
            },
        }
        manifest_path = output / "models_manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

        if destination_type == "docker_volume":
            if not docker_volume:
                raise ValueError("Selecciona un volumen Docker de destino.")
            notify("docker-copy", 94, f"Copiando archivos al volumen Docker {docker_volume}…")
            DockerFileManagerService.copy_local_tree_to_volume(models_root, docker_volume, docker_path, payload.overwrite)
            manifest["docker_destination"] = {"volume": docker_volume, "path": docker_path}
            manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

        if destination_type == "modal":
            from app.db.database import SessionLocal
            session = SessionLocal()
            try:
                from app.services.infrastructure_provider_service import InfrastructureProviderService
                modal_config = InfrastructureProviderService.get_modal(session)
                notify("modal-copy", 94, f"Subiendo archivos al volumen Modal {modal_config.volume_name}…")
                ModalFileManagerService.copy_tree(session, models_root, modal_config.volume_name, docker_path, payload.overwrite)
                manifest["modal_destination"] = {"volume": modal_config.volume_name, "path": docker_path}
                manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
            finally:
                session.close()

        if destination_type in {"runpod", "beam"}:
            from app.db.database import SessionLocal
            session = SessionLocal()
            try:
                if destination_type == "runpod":
                    details = RuntimeModelVolumeExportService._copy_to_runpod(session, models_root, docker_path, payload.overwrite, notify)
                    manifest["runpod_destination"] = details
                else:
                    details = RuntimeModelVolumeExportService._copy_to_beam(session, models_root, docker_path, payload.overwrite, notify)
                    manifest["beam_destination"] = details
                manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
            finally:
                session.close()

        notify("completed", 99, "Modelos organizados para Volume.")
        return {
            "success": True,
            "output_directory": str(output),
            "models_directory": str(models_root),
            "manifest_path": str(manifest_path),
            "destination_type": destination_type,
            "docker_volume": docker_volume if destination_type == "docker_volume" else None,
            "docker_path": docker_path if destination_type == "docker_volume" else None,
            "models_detected": len(records),
            "models_found": len(records) - missing,
            "models_missing": missing,
            "models_copied": copied,
            "models_skipped": skipped,
            "models_overwritten": overwritten,
            "errors": 0,
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "destination": (
                {"type": "docker_volume", "volume": docker_volume, "path": docker_path}
                if destination_type == "docker_volume"
                else ({"type": destination_type, "path": docker_path} if destination_type in {"modal", "runpod", "beam"} else {"type": "local", "path": str(output)})
            ),
            "bytes_copied": bytes_copied,
            "warnings": warnings,
            "manifest": manifest,
        }
