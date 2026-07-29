from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

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
        # The configuration can contain repeated logical references coming from
        # normal/API workflows. Export only one record per real physical file.
        # This is the final safety boundary shared by every destination.
        seen_sources: dict[str, dict[str, Any]] = {}
        seen_missing: set[str] = set()
        # Export Runtime and reproducible model-volume export must consume the
        # model list already analyzed and persisted in the selected profile.
        # Re-running the workflow resolver here couples export to UI workflow
        # parsing and can leave the job blocked in the initial progress phase.
        for item in [model for model in (config.models or []) if model.get("enabled", True)]:
            source = RuntimeContextGeneratorService._find_model(comfy, item)
            record = dict(item)
            if source is None:
                missing_key = str(item.get("target_path") or item.get("name") or "").replace("\\", "/").strip().casefold()
                if missing_key and missing_key in seen_missing:
                    continue
                if missing_key:
                    seen_missing.add(missing_key)
                record.update({"found": False, "source_path": None, "relative_path": None, "size_bytes": 0})
                records.append(record)
                continue

            source = source.resolve()
            # All destinations consume this same normalized target path. The
            # physical file may live outside ComfyUI/models through
            # extra_model_paths.yaml, so never call relative_to(models_root)
            # blindly here.
            try:
                from app.services.runtime_import_service import RuntimeImportService
                roots = RuntimeImportService._configured_model_roots(comfy)
                logical_path = RuntimeImportService._logical_model_path(source, roots)
            except Exception:
                logical_path = str(item.get("target_path") or source.name).replace("\\", "/").lstrip("/")
            logical_path = logical_path or source.name
            physical_key = str(source).casefold()
            existing = seen_sources.get(physical_key)
            if existing is not None:
                references = existing.setdefault("workflow_references", [])
                for reference in item.get("workflow_references") or []:
                    if reference not in references:
                        references.append(reference)
                continue

            record.update({
                "found": True,
                "source_path": str(source),
                "relative_path": f"models/{logical_path}",
                "target_path": logical_path,
                "size_bytes": source.stat().st_size,
            })
            seen_sources[physical_key] = record
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
        """Sincroniza modelos mediante un Pod temporal + SSH + rsync.

        Esta rama está completamente aislada de Exportar Runtime y de los
        destinos local, Docker, Modal y Beam.
        """
        from app.services.infrastructure_provider_service import InfrastructureProviderService
        from app.services.runpod_model_volume_sync import RunPodModelVolumeSyncService

        cfg = InfrastructureProviderService.get_runpod(session)
        return RunPodModelVolumeSyncService.sync_tree(
            api_key=str(cfg.api_key or ""),
            volume_id=str(cfg.network_volume_id or ""),
            data_center_id=str(cfg.data_center_id or ""),
            models_root=models_root,
            remote_path=remote_path,
            overwrite=overwrite,
            timeout_seconds=int(cfg.timeout_seconds or 900),
            notify=notify,
        )

    @staticmethod
    def _copy_to_beam(
        session,
        models_root: Path,
        remote_path: str,
        overwrite: bool,
        notify: ProgressCallback,
        logical_models: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Beam Upload Engine V4, aislado de Modal, RunPod y Docker.

        V4 abandona las copias individuales. Prepara un árbol filtrado y ejecuta
        una única operación ``beam cp <directorio> beam://<volumen>/<ruta>``;
        Beam CLI 0.2.207 selecciona multipart automáticamente cuando el Gateway
        dispone del servicio externo de archivos.
        """
        from app.services.infrastructure_provider_service import InfrastructureProviderService
        from app.services.beam_upload_engine_v4_service import BeamUploadEngineV4Service

        cfg = InfrastructureProviderService.get_beam(session)
        volume_name = str(cfg.volume_name or "").strip()
        if not volume_name:
            raise ValueError("Configura el nombre del volumen Beam antes de exportar.")

        physical_files = sorted(path for path in models_root.rglob("*") if path.is_file())
        physical_total = len(physical_files)
        bytes_total = sum(path.stat().st_size for path in physical_files)
        logical_total = len({
            str(item.get("target_path") or "").replace("\\", "/").strip("/")
            for item in logical_models
            if item.get("found", True) and item.get("target_path")
        })
        latest_percent = 94
        started = time.perf_counter()

        def human_bytes(value: int) -> str:
            amount = float(max(0, value))
            for unit in ("B", "KB", "MB", "GB", "TB"):
                if amount < 1024 or unit == "TB":
                    return f"{amount:.1f} {unit}" if unit != "B" else f"{int(amount)} B"
                amount /= 1024
            return f"{amount:.1f} TB"

        notify(
            "beam-v4-inventory",
            94,
            f"Beam V4: preparando una transferencia de directorio para {physical_total} archivos físicos "
            f"({logical_total} modelos lógicos), {human_bytes(bytes_total)} en total.",
        )

        def on_progress(event: dict[str, Any]) -> None:
            nonlocal latest_percent
            phase = str(event.get("phase") or "transfer-progress")
            transferred = int(event.get("bytes_transferred") or event.get("bytes_uploaded") or 0)
            pending_bytes = max(1, int(event.get("bytes_pending") or bytes_total or 1))
            ratio = min(1.0, max(0.0, transferred / pending_bytes))
            latest_percent = max(latest_percent, min(99, 94 + int(5 * ratio)))

            total = max(1, int(event.get("total") or physical_total or 1))
            uploaded = int(event.get("files_uploaded") or 0)
            skipped = int(event.get("files_skipped") or 0)
            queued_index = int(event.get("queue_index") or 0)
            queued_total = int(event.get("queued_total") or 0)
            completed_index = int(event.get("completed_index") or 0)
            name = str(event.get("file_name") or "")
            remote = str(event.get("remote") or "").replace("\\", "/")
            file_size = int(event.get("file_size") or 0)
            speed = int(event.get("speed_bps") or 0)
            native = str(event.get("native_line") or "").strip()
            eta = str(event.get("eta") or "").strip()

            if phase == "inventory":
                message = (
                    f"Beam V4: inventariando el volumen {volume_name} para una sola subida de directorio. "
                    f"CLI detectada: {event.get('cli_version') or 'desconocida'}"
                )
            elif phase == "file-skipped":
                message = (
                    f"Beam V4: OMITIDO {skipped}/{total} · {name} · {human_bytes(file_size)} · "
                    f"ya existe en {remote}."
                )
            elif phase == "file-queued":
                message = (
                    f"Beam V4: ARCHIVO PREPARADO {queued_index}/{queued_total} · {name} · "
                    f"{human_bytes(file_size)} · destino: {remote}"
                )
            elif phase == "transfer-start":
                message = (
                    f"Beam V4: iniciando UNA transferencia de directorio con multipart automático · "
                    f"{event.get('files_pending', 0)} archivos · "
                    f"{human_bytes(int(event.get('bytes_pending') or 0))} · "
                    f"destino: {event.get('destination', '')}"
                )
            elif phase == "transfer-progress":
                current = f" · archivo detectado: {name}" if name else ""
                message = (
                    f"Beam V4: SUBIENDO DIRECTORIO · {human_bytes(transferred)} de "
                    f"{human_bytes(int(event.get('bytes_pending') or bytes_total))}{current}"
                )
                if speed > 0:
                    message += f" · {human_bytes(speed)}/s"
                if eta:
                    message += f" · ETA {eta}"
                if native:
                    message += f" · Beam CLI: {native[-350:]}"
            elif phase == "file-completed":
                message = (
                    f"Beam V4: CONFIRMADO {completed_index}/{max(1, total - skipped)} · {name} · "
                    f"{human_bytes(file_size)} · {uploaded} subidos · {skipped} omitidos"
                )
            elif phase == "completed":
                elapsed = max(0.001, time.perf_counter() - started)
                average = int(int(event.get("bytes_uploaded") or 0) / elapsed)
                message = (
                    f"Beam V4 completado: {uploaded} archivos subidos en una sola operación, "
                    f"{skipped} omitidos, {human_bytes(int(event.get('bytes_uploaded') or 0))} transferidos"
                )
                if average > 0:
                    message += f" · media global {human_bytes(average)}/s"
            else:
                message = f"Beam V4: {phase} · {name}"
            notify(f"beam-v4-{phase}", latest_percent, message)

        try:
            result = BeamUploadEngineV4Service.upload_tree(
                session,
                volume=volume_name,
                models_root=models_root,
                remote_prefix=remote_path,
                overwrite=overwrite,
                timeout=max(3600, int(cfg.timeout_seconds or 900)),
                on_progress=on_progress,
            )
        except Exception as exc:
            raise RuntimeError(f"Beam V4 no pudo subir los modelos al volumen {volume_name}: {exc}") from exc

        notify(
            "beam-v4-copy",
            99,
            f"Beam V4 finalizado: {result['files_uploaded']} subidos mediante una sola transferencia, "
            f"{result['files_skipped']} omitidos, {logical_total} modelos lógicos preparados.",
        )
        return {
            "volume_name": volume_name,
            "path": str(result.get("path") or ""),
            "target": f"beam://{volume_name}" + (f"/{result.get('path')}" if result.get("path") else ""),
            "overwrite_requested": overwrite,
            "models_uploaded": logical_total,
            "files_total": int(result.get("files_total") or physical_total),
            "files_uploaded": int(result.get("files_uploaded") or 0),
            "files_skipped": int(result.get("files_skipped") or 0),
            "bytes_total": int(result.get("bytes_total") or bytes_total),
            "bytes_uploaded": int(result.get("bytes_uploaded") or 0),
            "bytes_skipped": int(result.get("bytes_skipped") or 0),
            "transfer_mode": "beam-v4-directory-multipart-auto",
            "transfer_modes": result.get("transfer_modes") or [],
            "parallel_workers": int(result.get("workers") or 0),
            "beam_cli_version": str(result.get("cli_version") or ""),
        }

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
        destination_type = getattr(payload, "destination_type", "local")
        output.mkdir(parents=True, exist_ok=True)
        # RunPod uploads the complete staging tree. Reusing the previous tree
        # leaked models from older workflows into the next upload (the apparent
        # extra audio encoder and repeated Qwen/VAE entries). Build a clean,
        # deterministic tree containing only the current validated models.
        if destination_type in {"runpod", "beam"} and models_root.exists():
            provider_label = "RunPod" if destination_type == "runpod" else "Beam"
            notify("preparing", 3, f"Limpiando la preparación anterior de {provider_label}…")
            shutil.rmtree(models_root)
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
            relative = Path(str(item.get("target_path") or source.name).replace("\\", "/").lstrip("/"))
            destination = models_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)

            # SAM3 es una categoría compuesta: el loader TBG requiere todos los
            # archivos y subdirectorios de models/sam3. Las demás categorías
            # continúan exportándose modelo por modelo.
            if relative.parts and relative.parts[0].lower() == "sam3" and not sam3_tree_processed:
                sam3_source = source.parent if len(relative.parts) == 1 else source.parents[len(relative.parts) - 2]
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
                    details = RuntimeModelVolumeExportService._copy_to_beam(
                        session,
                        models_root,
                        docker_path,
                        payload.overwrite,
                        notify,
                        [item for item in records if item.get("found")],
                    )
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
