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
        """Exportador Beam V2, aislado de Modal, RunPod y Docker.

        La barra principal representa archivos/bytes físicos ya procesados. El
        texto conserva también el total de modelos lógicos del manifiesto para
        evitar mezclar ambos conceptos. "Omitir existentes" consulta una sola
        vez cada carpeta remota y excluye archivos antes de transferirlos.
        """
        from app.services.infrastructure_provider_service import InfrastructureProviderService
        from app.services.beam_file_manager_service import BeamFileManagerService

        cfg = InfrastructureProviderService.get_beam(session)
        volume_name = str(cfg.volume_name or "").strip()
        if not volume_name:
            raise ValueError("Configura el nombre del volumen Beam antes de exportar.")

        files = sorted(path for path in models_root.rglob("*") if path.is_file())
        bytes_total = sum(path.stat().st_size for path in files)
        prefix = remote_path.replace("\\", "/").strip("/")
        upload_items: list[tuple[Path, str]] = []
        for path in files:
            relative = path.relative_to(models_root).as_posix()
            destination = "/".join(part for part in (prefix, relative) if part)
            upload_items.append((path, destination))

        logical_paths: list[str] = []
        for item in logical_models:
            if not item.get("found", True):
                continue
            target = str(item.get("target_path") or "").replace("\\", "/").strip("/")
            if target and target not in logical_paths:
                logical_paths.append(target)
        logical_total = len(logical_paths)
        physical_total = len(upload_items)
        transfer_started = time.perf_counter()
        latest_percent = 94
        last_confirmed_speed = 0.0

        def human_bytes(value: int) -> str:
            amount = float(max(0, value))
            for unit in ("B", "KB", "MB", "GB", "TB"):
                if amount < 1024 or unit == "TB":
                    return f"{amount:.1f} {unit}" if unit != "B" else f"{int(amount)} B"
                amount /= 1024
            return f"{amount:.1f} TB"

        notify(
            "beam-inventory",
            94,
            (
                f"Beam: preparando {physical_total} archivo{'s' if physical_total != 1 else ''} "
                f"({logical_total} modelo{'s' if logical_total != 1 else ''} lógicos). "
                + ("Se omitirán los archivos que ya existan." if not overwrite else "Se sobrescribirán los destinos existentes.")
            ),
        )

        def on_progress(event: dict[str, Any]) -> None:
            nonlocal latest_percent, last_confirmed_speed
            phase = str(event.get("phase") or "uploading")
            current = int(event.get("current") or 0)
            total = max(1, int(event.get("total") or physical_total or 1))
            processed_bytes = int(event.get("bytes_processed") or 0)
            uploaded_bytes = int(event.get("bytes_uploaded") or 0)
            total_bytes_event = max(1, int(event.get("bytes_total") or bytes_total or 1))
            skipped = int(event.get("files_skipped") or 0)
            remote = str(event.get("remote") or "").replace("\\", "/")

            # Los bytes completados son la medida principal; para archivos vacíos
            # o inventario se conserva el avance por cantidad de archivos.
            ratio_bytes = processed_bytes / total_bytes_event
            ratio_files = current / total
            ratio = max(ratio_bytes, ratio_files if total_bytes_event <= 1 else 0.0)
            percent = 94 + int(5 * min(1.0, max(0.0, ratio)))
            latest_percent = max(latest_percent, min(99, percent))

            elapsed = max(0.001, time.perf_counter() - transfer_started)
            # Beam CLI no expone progreso de bytes mientras un archivo sigue en
            # transferencia. ``bytes_uploaded`` aumenta únicamente cuando un
            # ``beam cp`` termina. Por eso nunca presentamos 0 B/s como si fuera
            # una medición real: hasta completar el primer archivo la velocidad
            # todavía no está disponible. Después mostramos una media confirmada
            # basada solo en bytes efectivamente terminados, nunca en omitidos.
            if uploaded_bytes > 0:
                last_confirmed_speed = uploaded_bytes / elapsed
            filename = remote.rsplit("/", 1)[-1] if remote else ""
            uploaded_files = int(event.get("files_uploaded") or 0)

            if phase == "inventory":
                message = f"Beam: comprobando archivos existentes en el volumen {volume_name}…"
            elif phase == "skipping":
                message = (
                    f"Beam: {current}/{total} archivos procesados · {skipped} omitidos · "
                    f"ya existía: {filename}"
                )
            elif phase == "completed":
                message = (
                    f"Beam completado: {current}/{total} archivos procesados · "
                    f"{human_bytes(processed_bytes)} de {human_bytes(total_bytes_event)} · "
                    f"{uploaded_files} subidos · {skipped} omitidos."
                )
            else:
                message = (
                    f"Beam: {current}/{total} archivos · {human_bytes(processed_bytes)} de "
                    f"{human_bytes(total_bytes_event)}"
                )
                if skipped:
                    message += f" · {skipped} omitidos"
                if last_confirmed_speed > 0:
                    message += f" · velocidad media confirmada: {human_bytes(int(last_confirmed_speed))}/s"
                elif current < total:
                    message += " · subiendo; velocidad disponible al completar el primer archivo"
                if filename:
                    message += f" · último completado: {filename}"
            notify(f"beam-{phase}", latest_percent, message)

        def on_completed(
            current: int,
            total: int,
            remote: str,
            uploaded_bytes: int,
            status: str = "uploaded",
        ) -> None:
            # Conservado como callback separado para compatibilidad y trazabilidad.
            del current, total, remote, uploaded_bytes, status

        try:
            result = BeamFileManagerService.upload_many(
                session,
                volume=volume_name,
                files=upload_items,
                timeout=max(3600, int(cfg.timeout_seconds or 900)),
                workers=4,
                overwrite=overwrite,
                on_completed=on_completed,
                on_progress=on_progress,
            )
        except Exception as exc:
            raise RuntimeError(
                f"Beam no pudo subir los modelos al volumen {volume_name}: {exc}"
            ) from exc

        uploaded_count = int(result.get("files_uploaded", 0))
        skipped_count = int(result.get("files_skipped", 0))
        uploaded_bytes = int(result.get("bytes_uploaded", 0))
        notify(
            "beam-copy",
            99,
            (
                f"Beam completado: {uploaded_count} archivos subidos, {skipped_count} omitidos, "
                f"{logical_total} modelos lógicos preparados."
            ),
        )
        return {
            "volume_name": volume_name,
            "path": prefix,
            "target": f"beam://{volume_name}" + (f"/{prefix}" if prefix else ""),
            "overwrite_requested": overwrite,
            "models_uploaded": logical_total,
            "files_total": physical_total,
            "files_uploaded": uploaded_count,
            "files_skipped": skipped_count,
            "bytes_total": int(result.get("bytes_total", bytes_total)),
            "bytes_uploaded": uploaded_bytes,
            "transfer_mode": "beam-v2-inventory-parallel-root-copy-real-progress",
            "parallel_workers": int(result.get("workers", 0)),
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
