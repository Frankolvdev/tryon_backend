import threading

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.models.runtime_builder_build import RuntimeBuilderBuild
from app.models.runtime_builder_config import RuntimeBuilderConfig
from app.models.runtime_project import RuntimeProject
from app.schemas.runtime_builder import (
    RuntimeBuildCreate,
    RuntimeBuildListResponse,
    RuntimeBuildResponse,
    RuntimeBuildBulkRequest,
    RuntimeBuildBulkResponse,
    RuntimeBuilderConfigResponse,
    RuntimeBuilderConfigUpdate,
    RuntimeBuilderProfileCreate,
    RuntimeBuilderProfileList,
    RuntimeBuilderProfileSummary,
    RuntimeContextGenerateRequest,
    RuntimeContextJobCreateResponse,
    RuntimeContextJobResponse,
    RuntimeDockerDiagnosticResponse,
    RuntimeGeneratedFilesResponse,
    RuntimeImportApplyRequest,
    RuntimeImportPathRequest,
    RuntimeIntelligenceIndexRequest,
    RuntimeIntelligenceSearchRequest,
    RuntimeLaunchPreview,
    RuntimeLaunchSettings,
    RuntimeModelExportSettings,
    RuntimeModelVolumeAnalyzeRequest,
    RuntimeModelVolumeExportRequest,
    RuntimeProjectResponse,
    RuntimeValidationResponse,
    RuntimeWorkflowAnalysisRequest,
    RuntimeWorkflowResolveRequest,
    RuntimeWorkspaceUpdate,
)
from app.services.runtime_build_execution_service import RuntimeBuildExecutionService
from app.services.infrastructure_provider_service import InfrastructureProviderService
from app.services.runtime_builder_service import RuntimeBuilderService
from app.services.runtime_context_job_service import RuntimeContextJobService
from app.services.runtime_import_service import RuntimeImportService
from app.services.runtime_intelligence_service import RuntimeIntelligenceService
from app.services.runtime_model_volume_export_service import RuntimeModelVolumeExportService

router = APIRouter(prefix="/runtime-builder", dependencies=[Depends(admin_guard)])


def get_or_create(db: Session) -> RuntimeBuilderConfig:
    config = db.query(RuntimeBuilderConfig).order_by(RuntimeBuilderConfig.is_active.desc(), RuntimeBuilderConfig.id.asc()).first()
    if config is None:
        config = RuntimeBuilderConfig()
        db.add(config)
        db.commit()
        db.refresh(config)

    changed = False
    safe_name = RuntimeBuilderService.sanitize_runtime_name(
        getattr(config, "runtime_name", None)
    )
    if config.runtime_name != safe_name:
        config.runtime_name = safe_name
        changed = True

    profile = RuntimeBuilderService.RECOMMENDED_PROFILE
    profile_values = {
        "python_version": profile["python_version"],
        "cuda_version": profile["cuda_version"],
        "pytorch_index_url": profile["pytorch_index_url"],
        "comfyui_commit": profile["comfyui_commit"],
        "include_comfyui_manager": True,
        "target_platform": "linux/amd64",
    }
    for field, value in profile_values.items():
        if getattr(config, field) != value:
            setattr(config, field, value)
            changed = True

    merged_nodes = RuntimeBuilderService.merge_required_custom_nodes(config.custom_nodes)
    if merged_nodes != (config.custom_nodes or []):
        config.custom_nodes = merged_nodes
        changed = True

    if changed:
        db.add(config)
        db.commit()
        db.refresh(config)
    return config


def get_or_create_project(
    db: Session,
    config: RuntimeBuilderConfig | None = None,
) -> RuntimeProject:
    config = config or get_or_create(db)
    project = (
        db.query(RuntimeProject)
        .filter(RuntimeProject.project_key == config.project_key)
        .first()
    )
    if project is None:
        project = RuntimeProject(
            runtime_config_id=config.id,
            project_key=config.project_key,
            module_type=config.module_type,
            source_comfyui_path=config.source_comfyui_path,
            workflow_filename=config.workflow_filename,
            workflow_json=config.workflow_json,
            container_workdir=config.container_workdir or "/app",
            export_root_directory=config.export_root_directory,
            export_directory=config.export_directory,
            last_index_summary=config.last_index_summary,
            workspace_status=config.workspace_status or "draft",
            last_export_archive=config.last_export_archive,
            last_export_manifest=config.last_export_manifest,
            last_exported_at=config.last_exported_at,
        )
        db.add(project)
        db.commit()
        db.refresh(project)
    return project


def sync_project_to_config(
    project: RuntimeProject,
    config: RuntimeBuilderConfig,
) -> None:
    for field in (
        "project_key",
        "module_type",
        "source_comfyui_path",
        "workflow_filename",
        "workflow_json",
        "container_workdir",
        "export_root_directory",
        "export_directory",
        "last_index_summary",
        "workspace_status",
        "last_export_archive",
        "last_export_manifest",
        "last_exported_at",
    ):
        setattr(config, field, getattr(project, field))



@router.get("/profiles", response_model=RuntimeBuilderProfileList)
def list_profiles(db: Session = Depends(get_db)):
    get_or_create(db)
    return RuntimeBuilderProfileList(items=db.query(RuntimeBuilderConfig).order_by(RuntimeBuilderConfig.created_at.asc()).all())

@router.post("/profiles", response_model=RuntimeBuilderConfigResponse, status_code=201)
def create_profile(payload: RuntimeBuilderProfileCreate, db: Session = Depends(get_db)):
    base = get_or_create(db)
    slug = RuntimeBuilderService.sanitize_runtime_name(payload.name)
    for row in db.query(RuntimeBuilderConfig).all(): row.is_active = False
    config = RuntimeBuilderConfig(
        name=payload.name, provider=payload.provider, is_active=True, runtime_name=slug,
        runtime_version="1.0.0", python_version=base.python_version, cuda_version=base.cuda_version,
        pytorch_index_url=base.pytorch_index_url, comfyui_repository=base.comfyui_repository,
        comfyui_commit=base.comfyui_commit, target_platform=base.target_platform,
        registry_image=f"ghcr.io/your-org/{slug}", include_comfyui_manager=True,
        custom_nodes=RuntimeBuilderService.merge_required_custom_nodes([]), python_dependencies=[], models=[],
        environment_variables=[], volumes=[], project_key=f"{slug}-{int(__import__('time').time())}", module_type=slug,
        container_workdir="/app", workspace_status="draft"
    )
    db.add(config); db.commit(); db.refresh(config)
    get_or_create_project(db, config)
    return config

@router.post("/profiles/{profile_id}/select", response_model=RuntimeBuilderConfigResponse)
def select_profile(profile_id: int, db: Session = Depends(get_db)):
    selected = db.get(RuntimeBuilderConfig, profile_id)
    if selected is None: raise HTTPException(status_code=404, detail="Runtime profile not found")
    for row in db.query(RuntimeBuilderConfig).all(): row.is_active = row.id == profile_id
    db.commit(); db.refresh(selected)
    return selected

def _delete_profile(profile_id: int, db: Session) -> None:
    selected = db.query(RuntimeBuilderConfig).filter(RuntimeBuilderConfig.id == profile_id).first()
    if selected is None:
        raise HTTPException(status_code=404, detail="Runtime profile not found")
    if db.query(RuntimeBuilderConfig).count() <= 1:
        raise HTTPException(status_code=409, detail="At least one runtime profile is required")

    was_active = bool(selected.is_active)
    db.delete(selected)
    db.commit()

    if was_active:
        fallback = (
            db.query(RuntimeBuilderConfig)
            .order_by(RuntimeBuilderConfig.id.asc())
            .first()
        )
        if fallback is not None:
            fallback.is_active = True
            db.add(fallback)
            db.commit()


@router.delete("/profiles/{profile_id}", status_code=200)
def delete_profile(profile_id: int, db: Session = Depends(get_db)):
    _delete_profile(profile_id, db)
    # browserApiRequest espera una respuesta JSON. Un 204 vacío eliminaba el
    # perfil correctamente, pero el BackOffice lo mostraba como error al intentar
    # interpretar el cuerpo inexistente.
    return {"success": True, "deleted_profile_id": profile_id}


@router.post("/profiles/{profile_id}/delete", status_code=200)
def delete_profile_compat(profile_id: int, db: Session = Depends(get_db)):
    """Compatibility endpoint for proxies/environments that mishandle DELETE routes."""
    _delete_profile(profile_id, db)
    return {"success": True, "deleted_profile_id": profile_id}


@router.get("/config", response_model=RuntimeBuilderConfigResponse)
def read_config(db: Session = Depends(get_db)):
    return get_or_create(db)


@router.put("/config", response_model=RuntimeBuilderConfigResponse)
def update_config(
    payload: RuntimeBuilderConfigUpdate,
    db: Session = Depends(get_db),
):
    config = get_or_create(db)
    values = payload.model_dump()
    # El proveedor pertenece al runtime desde su creación y no puede cambiarse al editarlo.
    values["provider"] = config.provider
    profile = RuntimeBuilderService.RECOMMENDED_PROFILE
    values.update(
        {
            "python_version": profile["python_version"],
            "cuda_version": profile["cuda_version"],
            "pytorch_index_url": profile["pytorch_index_url"],
            "comfyui_commit": profile["comfyui_commit"],
            "include_comfyui_manager": True,
            "target_platform": "linux/amd64",
            "custom_nodes": RuntimeBuilderService.merge_required_custom_nodes(
                values.get("custom_nodes")
            ),
        }
    )
    for field, value in values.items():
        setattr(config, field, value)
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


@router.get("/project", response_model=RuntimeProjectResponse)
def read_project(db: Session = Depends(get_db)):
    return get_or_create_project(db)


@router.patch("/project", response_model=RuntimeProjectResponse)
def update_project(
    payload: RuntimeWorkspaceUpdate,
    db: Session = Depends(get_db),
):
    config = get_or_create(db)
    project = get_or_create_project(db, config)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    sync_project_to_config(project, config)
    db.add_all([project, config])
    db.commit()
    db.refresh(project)
    return project


@router.patch("/workspace", response_model=RuntimeProjectResponse)
def update_workspace(
    payload: RuntimeWorkspaceUpdate,
    db: Session = Depends(get_db),
):
    return update_project(payload, db)


@router.post("/validate", response_model=RuntimeValidationResponse)
def validate_config(db: Session = Depends(get_db)):
    return RuntimeBuilderService.validate(get_or_create(db))


@router.post("/generate", response_model=RuntimeGeneratedFilesResponse)
def generate_files(db: Session = Depends(get_db)):
    modal_config = InfrastructureProviderService.get_modal(db)
    return RuntimeBuilderService.generate(
        get_or_create(db),
        modal_volume_name=modal_config.volume_name,
    )


@router.get("/diagnostic", response_model=RuntimeDockerDiagnosticResponse)
def diagnostic(db: Session = Depends(get_db)):
    return RuntimeBuildExecutionService.diagnostic(db)


@router.get("/deployment-providers")
def deployment_providers(db: Session = Depends(get_db)):
    return {
        "items": RuntimeBuildExecutionService.deployment_providers(db),
    }


@router.get("/builds", response_model=RuntimeBuildListResponse)
def list_builds(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    # Build history is scoped to the currently selected runtime profile.
    # RuntimeBuilderBuild already persists runtime_config_id when a build is
    # created, so no schema, migration or build execution change is needed.
    config = get_or_create(db)
    query = db.query(RuntimeBuilderBuild).filter(
        RuntimeBuilderBuild.runtime_config_id == config.id
    )
    return {
        "items": query.order_by(RuntimeBuilderBuild.id.desc()).limit(limit).all(),
        "total": query.count(),
    }


@router.post("/builds", response_model=RuntimeBuildResponse)
def create_build(
    payload: RuntimeBuildCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    try:
        build = RuntimeBuildExecutionService.create(db, get_or_create(db))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    background_tasks.add_task(
        RuntimeBuildExecutionService.start,
        build.id,
        payload.push_after_build,
    )
    return build


@router.get("/builds/{build_id}", response_model=RuntimeBuildResponse)
def read_build(build_id: int, db: Session = Depends(get_db)):
    item = db.get(RuntimeBuilderBuild, build_id)
    if not item:
        raise HTTPException(404, "Build no encontrado.")
    return item


@router.post("/builds/{build_id}/publish", response_model=RuntimeBuildResponse)
def publish(
    build_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    item = db.get(RuntimeBuilderBuild, build_id)
    if not item:
        raise HTTPException(404, "Build no encontrado.")
    background_tasks.add_task(RuntimeBuildExecutionService.publish, item.id)
    return item


@router.post("/builds/{build_id}/activate", response_model=RuntimeBuildResponse)
def activate(build_id: int, db: Session = Depends(get_db)):
    item = db.get(RuntimeBuilderBuild, build_id)
    if not item:
        raise HTTPException(404, "Build no encontrado.")
    try:
        return RuntimeBuildExecutionService.activate(db, item)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/builds/{build_id}/cancel", response_model=RuntimeBuildResponse)
def cancel(build_id: int, db: Session = Depends(get_db)):
    item = db.get(RuntimeBuilderBuild, build_id)
    if not item:
        raise HTTPException(404, "Build no encontrado.")
    if item.status in {"building", "pending", "validating", "publishing"}:
        item.status = "cancelled"
        item.phase = "cancelled"
        db.add(item)
        db.commit()
        db.refresh(item)
    return item



@router.post("/builds/{build_id}/deployments")
def create_deployment(
    build_id: int,
    payload: dict,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    item = db.get(RuntimeBuilderBuild, build_id)
    if not item:
        raise HTTPException(404, "Build no encontrado.")

    runtime_config = db.get(RuntimeBuilderConfig, item.runtime_config_id)
    if runtime_config is None:
        raise HTTPException(422, "La compilación no tiene un runtime asociado.")
    provider = str(runtime_config.provider or "").strip()
    if not provider:
        raise HTTPException(422, "El runtime no tiene proveedor asociado.")

    try:
        deployment = RuntimeBuildExecutionService.create_deployment(
            db,
            item,
            provider,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    background_tasks.add_task(
        RuntimeBuildExecutionService.run_deployment,
        item.id,
        deployment["id"],
    )
    return deployment



@router.post("/builds/bulk-cancel", response_model=RuntimeBuildBulkResponse)
def bulk_cancel_builds(payload: RuntimeBuildBulkRequest, db: Session = Depends(get_db)):
    active_statuses = {"building", "pending", "validating", "publishing"}
    items = db.query(RuntimeBuilderBuild).filter(RuntimeBuilderBuild.id.in_(payload.ids)).all()
    by_id = {item.id: item for item in items}
    affected_ids: list[int] = []
    skipped_ids: list[int] = []
    for build_id in payload.ids:
        item = by_id.get(build_id)
        if item is None or item.status not in active_statuses:
            skipped_ids.append(build_id)
            continue
        item.status = "cancelled"
        item.phase = "cancelled"
        db.add(item)
        affected_ids.append(build_id)
    db.commit()
    return RuntimeBuildBulkResponse(affected_ids=affected_ids, skipped_ids=skipped_ids)


@router.post("/builds/bulk-delete", response_model=RuntimeBuildBulkResponse)
def bulk_delete_builds(payload: RuntimeBuildBulkRequest, db: Session = Depends(get_db)):
    active_statuses = {"building", "pending", "validating", "publishing"}
    items = db.query(RuntimeBuilderBuild).filter(RuntimeBuilderBuild.id.in_(payload.ids)).all()
    by_id = {item.id: item for item in items}
    affected_ids: list[int] = []
    skipped_ids: list[int] = []
    for build_id in payload.ids:
        item = by_id.get(build_id)
        if item is None or item.status in active_statuses or item.active:
            skipped_ids.append(build_id)
            continue
        db.delete(item)
        affected_ids.append(build_id)
    db.commit()
    return RuntimeBuildBulkResponse(affected_ids=affected_ids, skipped_ids=skipped_ids)

@router.post("/import/scan-path")
def import_scan_path(payload: RuntimeImportPathRequest):
    try:
        return RuntimeImportService.scan_path(
            payload.path,
            payload.include_all_models,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/import/upload")
async def import_upload(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(422, "Debes cargar un archivo ZIP.")
    content = await file.read()
    if len(content) > 100 * 1024 * 1024:
        raise HTTPException(413, "El inventario supera el límite de 100 MB.")
    try:
        return RuntimeImportService.scan_inventory_zip(content)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/import/analyze-workflow")
def import_analyze_workflow(payload: RuntimeWorkflowAnalysisRequest):
    return RuntimeImportService.analyze_workflow(payload.workflow, payload.report)


@router.post("/import/apply", response_model=RuntimeBuilderConfigResponse)
def import_apply(
    payload: RuntimeImportApplyRequest,
    db: Session = Depends(get_db),
):
    return RuntimeImportService.apply_report(
        db,
        get_or_create(db),
        payload.report,
        payload.selection,
    )


@router.post("/import/resolve-workflow")
def import_resolve_workflow(
    payload: RuntimeWorkflowResolveRequest,
    db: Session = Depends(get_db),
):
    try:
        result = RuntimeImportService.resolve_current_workflow(
            payload.path,
            payload.workflow,
        )
        config = get_or_create(db)
        project = get_or_create_project(db, config)
        project.source_comfyui_path = payload.path
        project.workflow_json = payload.workflow
        project.workflow_filename = payload.workflow_filename
        project.workspace_status = "workflow_resolved"
        sync_project_to_config(project, config)
        db.add_all([project, config])
        db.commit()
        db.refresh(project)
        return result
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/intelligence/index")
def intelligence_index(
    payload: RuntimeIntelligenceIndexRequest,
    db: Session = Depends(get_db),
):
    try:
        result = RuntimeIntelligenceService.build_index(payload.path)
        config = get_or_create(db)
        project = get_or_create_project(db, config)
        project.source_comfyui_path = payload.path
        project.last_index_summary = result.get("summary") or {}
        project.workspace_status = "indexed"
        sync_project_to_config(project, config)
        db.add_all([project, config])
        db.commit()
        return result
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/intelligence/search")
def intelligence_search(payload: RuntimeIntelligenceSearchRequest):
    try:
        index = RuntimeIntelligenceService.build_index(payload.path)
        return {
            "items": RuntimeIntelligenceService.search(index, payload.query),
            "summary": index["summary"],
        }
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post(
    "/context/generate",
    response_model=RuntimeContextJobCreateResponse,
    status_code=202,
)
def generate_runtime_context(
    payload: RuntimeContextGenerateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    config = get_or_create(db)
    job = RuntimeContextJobService.create(config.id, payload)
    background_tasks.add_task(RuntimeContextJobService.run, job["job_id"])
    return job


@router.get(
    "/context/jobs/{job_id}",
    response_model=RuntimeContextJobResponse,
)
def read_runtime_context_job(job_id: str):
    try:
        return RuntimeContextJobService.public(job_id)
    except KeyError as exc:
        raise HTTPException(
            404,
            "Trabajo de exportación no encontrado o el backend fue reiniciado.",
        ) from exc


def _mega3_settings(config: RuntimeBuilderConfig) -> dict:
    manifest = dict(config.last_export_manifest or {})
    return dict(manifest.get("mega3_settings") or {})


def _save_mega3_settings(
    db: Session,
    config: RuntimeBuilderConfig,
    section: str,
    values: dict,
) -> None:
    manifest = dict(config.last_export_manifest or {})
    settings = dict(manifest.get("mega3_settings") or {})
    settings[section] = values
    manifest["mega3_settings"] = settings
    config.last_export_manifest = manifest
    db.add(config)
    db.commit()
    db.refresh(config)


def _docker_image_reference(payload: RuntimeLaunchSettings) -> str:
    image_name = str(payload.image_name or "").strip()
    if image_name:
        return image_name

    build_name = str(payload.build_name or "").strip()
    if not build_name:
        return "tryon-runtime:latest"

    last_slash = build_name.rfind("/")
    last_colon = build_name.rfind(":")
    return build_name if last_colon > last_slash else f"{build_name}:latest"


def _runtime_command(payload: RuntimeLaunchSettings) -> RuntimeLaunchPreview:
    parts = ["docker run", "-it"]

    # --rm no puede combinarse con una política de reinicio.
    if payload.restart_policy == "no":
        parts.append("--rm")
    else:
        parts.append(f"--restart {payload.restart_policy}")

    if payload.container_name.strip():
        parts.append(f"--name {payload.container_name.strip()}")

    if payload.gpu_mode in {"nvidia", "auto"}:
        parts.append("--gpus all")

    parts.append(f"-p {payload.host_port}:{payload.container_port}")

    mounts = (
        (payload.models_volume, payload.models_mount_path),
        (payload.workflows_volume, payload.workflows_mount_path),
        (payload.output_volume, payload.output_mount_path),
    )
    for volume, mount_path in mounts:
        normalized_volume = str(volume or "").strip()
        normalized_mount = str(mount_path or "").strip()
        if normalized_volume and normalized_mount:
            parts.append(f"-v {normalized_volume}:{normalized_mount}")

    for argument in payload.extra_arguments:
        normalized_argument = str(argument or "").strip()
        if normalized_argument:
            parts.append(normalized_argument)

    parts.append(_docker_image_reference(payload))
    lines = [parts[0]] + [f"  {item}" for item in parts[1:]]

    return RuntimeLaunchPreview(
        command=" \
".join(lines),
        lines=lines,
    )


@router.get(
    "/models-volume/settings",
    response_model=RuntimeModelExportSettings,
)
def read_model_export_settings(db: Session = Depends(get_db)):
    config = get_or_create(db)
    stored = dict(_mega3_settings(config).get("model_export") or {})
    if stored.get("docker_path") == "models":
        stored["docker_path"] = ""
    defaults = RuntimeModelExportSettings(
        comfyui_path=config.source_comfyui_path or "",
        output_directory=config.export_root_directory or "",
    )
    return defaults.model_copy(update=stored)


@router.put(
    "/models-volume/settings",
    response_model=RuntimeModelExportSettings,
)
def update_model_export_settings(
    payload: RuntimeModelExportSettings,
    db: Session = Depends(get_db),
):
    config = get_or_create(db)
    values = payload.model_dump()
    config.source_comfyui_path = payload.comfyui_path or None
    config.export_root_directory = payload.output_directory or None
    _save_mega3_settings(db, config, "model_export", values)
    return RuntimeModelExportSettings.model_validate(values)


@router.get(
    "/runtime-launch/settings",
    response_model=RuntimeLaunchSettings,
)
def read_runtime_launch_settings(db: Session = Depends(get_db)):
    config = get_or_create(db)
    stored = dict(_mega3_settings(config).get("runtime_launch") or {})
    defaults = RuntimeLaunchSettings(
        build_name=config.runtime_name or "tryon-runtime",
        image_name=config.registry_image or "tryon-runtime:latest",
    )
    return defaults.model_copy(update=stored)


@router.put(
    "/runtime-launch/settings",
    response_model=RuntimeLaunchSettings,
)
def update_runtime_launch_settings(
    payload: RuntimeLaunchSettings,
    db: Session = Depends(get_db),
):
    config = get_or_create(db)
    values = payload.model_dump()
    config.name = payload.build_name
    config.runtime_name = payload.build_name
    config.registry_image = payload.image_name
    _save_mega3_settings(db, config, "runtime_launch", values)
    stored = dict(_mega3_settings(config).get("runtime_launch") or {})
    return RuntimeLaunchSettings.model_validate(stored)


@router.post(
    "/runtime-launch/preview",
    response_model=RuntimeLaunchPreview,
)
def preview_runtime_launch(payload: RuntimeLaunchSettings):
    return _runtime_command(payload)


@router.post("/models-volume/analyze")
def analyze_models_volume(
    payload: RuntimeModelVolumeAnalyzeRequest,
    db: Session = Depends(get_db),
):
    try:
        return RuntimeModelVolumeExportService.analyze(
            get_or_create(db),
            payload.comfyui_path,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post(
    "/models-volume/export",
    response_model=RuntimeContextJobCreateResponse,
    status_code=202,
)
def export_models_volume(
    payload: RuntimeModelVolumeExportRequest,
    db: Session = Depends(get_db),
):
    config = get_or_create(db)
    _save_mega3_settings(
        db,
        config,
        "model_export",
        {
            "comfyui_path": payload.comfyui_path,
            "output_directory": payload.output_directory or "",
            "destination_type": payload.destination_type,
            "docker_volume": payload.docker_volume or "",
            "docker_path": payload.docker_path,
            "calculate_sha256": payload.calculate_sha256,
            "overwrite": payload.overwrite,
            "skip_identical": payload.skip_identical,
        },
    )

    job = RuntimeContextJobService.create_model_volume(config.id, payload)
    RuntimeContextJobService._update(
        job["job_id"],
        status="queued",
        phase="starting",
        progress=1,
        message="Iniciando exportación de modelos…",
    )
    public_job = RuntimeContextJobService.public(job["job_id"])

    worker = threading.Thread(
        target=RuntimeContextJobService.run_model_volume,
        args=(job["job_id"],),
        name=f"runtime-model-export-{job['job_id'][:8]}",
        daemon=True,
    )
    worker.start()
    return public_job
