from __future__ import annotations

import threading
import traceback
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.db.database import SessionLocal
from app.services.runtime_context_generator_service import RuntimeContextGeneratorService


class RuntimeContextJobService:
    """In-process registry for long-running local runtime exports."""

    _jobs: dict[str, dict[str, Any]] = {}
    _lock = threading.RLock()

    @classmethod
    def create(cls, config_id: int, payload: Any) -> dict[str, Any]:
        job_id = str(uuid4())
        now = datetime.now(timezone.utc).isoformat()
        job = {
            "job_id": job_id,
            "status": "queued",
            "phase": "queued",
            "progress": 0,
            "message": "Exportación en cola.",
            "error": None,
            "result": None,
            "created_at": now,
            "started_at": None,
            "finished_at": None,
            "config_id": config_id,
            "payload": payload.model_dump(),
        }
        with cls._lock:
            cls._jobs[job_id] = job
        return cls.public(job_id)

    @classmethod
    def public(cls, job_id: str) -> dict[str, Any]:
        with cls._lock:
            job = cls._jobs.get(job_id)
            if job is None:
                raise KeyError(job_id)
            result = deepcopy(job)
        result.pop("config_id", None)
        result.pop("payload", None)
        return result

    @classmethod
    def _update(cls, job_id: str, **values: Any) -> None:
        with cls._lock:
            if job_id in cls._jobs:
                cls._jobs[job_id].update(values)


    @classmethod
    def create_model_volume(cls, config_id: int, payload: Any) -> dict[str, Any]:
        job = cls.create(config_id, payload)
        job_id = job["job_id"]
        cls._update(job_id, message="Exportación de modelos en cola.", job_type="models_volume")
        return cls.public(job_id)

    @classmethod
    def run_model_volume(cls, job_id: str) -> None:
        from app.models.runtime_builder_config import RuntimeBuilderConfig
        from app.schemas.runtime_builder import RuntimeModelVolumeExportRequest
        from app.services.runtime_model_volume_export_service import RuntimeModelVolumeExportService

        try:
            with cls._lock:
                stored = deepcopy(cls._jobs[job_id])
            payload = RuntimeModelVolumeExportRequest(**stored["payload"])
            config_id = int(stored["config_id"])
            cls._update(
                job_id,
                status="running",
                phase="analyzing",
                progress=1,
                message="Preparando exportación de modelos…",
                started_at=datetime.now(timezone.utc).isoformat(),
            )

            def progress(phase: str, percent: int, message: str, details: dict[str, Any] | None = None) -> None:
                from app.services.beam_engine.beam_progress_service import BeamProgressService
                if BeamProgressService.is_cancelled(job_id):
                    return
                cls._update(
                    job_id,
                    status="running",
                    phase=phase,
                    progress=max(1, min(99, int(percent))),
                    message=message,
                    details=details,
                )

            db = SessionLocal()
            try:
                config = db.get(RuntimeBuilderConfig, config_id)
                if config is None:
                    raise ValueError("La configuración del Runtime Builder ya no existe.")
                from app.services.beam_engine.beam_progress_service import BeamProgressService
                BeamProgressService.bind_job(job_id)
                try:
                    result = RuntimeModelVolumeExportService.export(config, payload, progress)
                finally:
                    BeamProgressService.unbind_job()
                    BeamProgressService.clear(job_id)
            finally:
                db.close()

            from app.services.beam_engine.beam_progress_service import BeamProgressService
            if BeamProgressService.is_cancelled(job_id):
                cls._update(
                    job_id,
                    status="cancelled",
                    phase="cancelled",
                    message="Sincronización Beam cancelada.",
                    finished_at=datetime.now(timezone.utc).isoformat(),
                )
                return

            cls._update(
                job_id,
                status="completed",
                phase="completed",
                progress=100,
                message="Modelos exportados y organizados para Volume.",
                result=result,
                finished_at=datetime.now(timezone.utc).isoformat(),
            )
        except Exception as exc:  # noqa: BLE001
            from app.services.beam_engine.beam_multipart_client import BeamUploadCancelled
            from app.services.beam_engine.beam_progress_service import BeamProgressService
            cancelled = isinstance(exc, BeamUploadCancelled) or BeamProgressService.is_cancelled(job_id)
            cls._update(
                job_id,
                status="cancelled" if cancelled else "failed",
                phase="cancelled" if cancelled else "failed",
                message=(
                    "Sincronización Beam cancelada."
                    if cancelled
                    else "La exportación de modelos no pudo completarse."
                ),
                error=None if cancelled else str(exc),
                finished_at=datetime.now(timezone.utc).isoformat(),
            )
            if not cancelled:
                traceback.print_exc()

    @classmethod
    def run(cls, job_id: str) -> None:
        from app.common.time import utc_now
        from app.models.runtime_builder_config import RuntimeBuilderConfig
        from app.models.runtime_project import RuntimeProject
        from app.schemas.runtime_builder import RuntimeContextGenerateRequest

        try:
            with cls._lock:
                stored = deepcopy(cls._jobs[job_id])
            payload = RuntimeContextGenerateRequest(**stored["payload"])
            config_id = int(stored["config_id"])
            cls._update(
                job_id,
                status="running",
                phase="preparing",
                progress=1,
                message="Preparando la exportación reproducible…",
                started_at=datetime.now(timezone.utc).isoformat(),
            )

            def progress(phase: str, percent: int, message: str) -> None:
                cls._update(
                    job_id,
                    status="running",
                    phase=phase,
                    progress=max(1, min(99, int(percent))),
                    message=message,
                )

            db = SessionLocal()
            try:
                config = db.get(RuntimeBuilderConfig, config_id)
                if config is None:
                    raise ValueError("La configuración del Runtime Builder ya no existe.")
                modal_volume_name = None
                if str(getattr(config, "provider", "") or "").strip().lower() == "modal":
                    from app.services.infrastructure_provider_service import InfrastructureProviderService
                    modal_config = InfrastructureProviderService.get_modal(db)
                    modal_volume_name = modal_config.volume_name

                result = RuntimeContextGeneratorService.generate(
                    config,
                    payload,
                    progress,
                    modal_volume_name=modal_volume_name,
                )
                project = db.query(RuntimeProject).filter(
                    RuntimeProject.project_key == config.project_key
                ).first()
                if project is None:
                    project = RuntimeProject(
                        runtime_config_id=config.id,
                        project_key=config.project_key,
                        module_type=config.module_type,
                        container_workdir=config.container_workdir or "/app",
                    )
                    db.add(project)
                project.source_comfyui_path = payload.comfyui_path
                project.export_root_directory = result.get("export_root_directory")
                project.export_directory = result["output_directory"]
                project.workspace_status = "generated"
                project.last_export_archive = None
                project.last_export_manifest = result.get("manifest") or {}
                project.last_exported_at = utc_now()
                for field in (
                    "project_key", "module_type", "source_comfyui_path", "workflow_filename",
                    "workflow_json", "container_workdir", "export_root_directory",
                    "export_directory", "last_index_summary", "workspace_status",
                    "last_export_archive", "last_export_manifest", "last_exported_at",
                ):
                    setattr(config, field, getattr(project, field))
                db.add_all([project, config])
                db.commit()
            finally:
                db.close()

            cls._update(
                job_id,
                status="completed",
                phase="completed",
                progress=100,
                message="Contexto de runtime generado correctamente, sin ZIP de respaldo.",
                result=result,
                finished_at=datetime.now(timezone.utc).isoformat(),
            )
        except Exception as exc:  # noqa: BLE001
            cls._update(
                job_id,
                status="failed",
                phase="failed",
                message="La exportación no pudo completarse.",
                error=str(exc),
                finished_at=datetime.now(timezone.utc).isoformat(),
            )
            traceback.print_exc()
