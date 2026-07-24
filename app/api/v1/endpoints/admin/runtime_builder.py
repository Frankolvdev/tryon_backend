from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session
from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.models.runtime_builder_config import RuntimeBuilderConfig
from app.models.runtime_builder_build import RuntimeBuilderBuild
from app.models.runtime_project import RuntimeProject
from app.schemas.runtime_builder import RuntimeBuilderConfigResponse, RuntimeBuilderConfigUpdate, RuntimeGeneratedFilesResponse, RuntimeValidationResponse, RuntimeBuildCreate, RuntimeBuildResponse, RuntimeBuildListResponse, RuntimeBuildBulkRequest, RuntimeBuildBulkResponse, RuntimeDockerDiagnosticResponse, RuntimeImportPathRequest, RuntimeImportApplyRequest, RuntimeWorkflowAnalysisRequest, RuntimeWorkflowResolveRequest, RuntimeIntelligenceIndexRequest, RuntimeIntelligenceSearchRequest, RuntimeContextGenerateRequest, RuntimeContextGenerateResponse, RuntimeContextJobCreateResponse, RuntimeContextJobResponse, RuntimeWorkspaceUpdate, RuntimeProjectResponse, RuntimeModelVolumeAnalyzeRequest, RuntimeModelVolumeExportRequest
from app.services.runtime_builder_service import RuntimeBuilderService
from app.services.runtime_build_execution_service import RuntimeBuildExecutionService
from app.services.runtime_import_service import RuntimeImportService
from app.services.runtime_intelligence_service import RuntimeIntelligenceService
from app.services.runtime_context_generator_service import RuntimeContextGeneratorService
from app.services.runtime_context_job_service import RuntimeContextJobService
from app.services.runtime_model_volume_export_service import RuntimeModelVolumeExportService
router=APIRouter(prefix="/runtime-builder",dependencies=[Depends(admin_guard)])

def get_or_create(db):
    config=db.query(RuntimeBuilderConfig).order_by(RuntimeBuilderConfig.id.asc()).first()
    if config is None:
        config=RuntimeBuilderConfig()
        db.add(config); db.commit(); db.refresh(config)
    changed = False
    safe_name = RuntimeBuilderService.sanitize_runtime_name(getattr(config, "runtime_name", None))
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
        db.add(config); db.commit(); db.refresh(config)
    return config

def get_or_create_project(db: Session, config: RuntimeBuilderConfig | None = None) -> RuntimeProject:
    config = config or get_or_create(db)
    project = db.query(RuntimeProject).filter(RuntimeProject.project_key == config.project_key).first()
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
        db.add(project); db.commit(); db.refresh(project)
    return project

def sync_project_to_config(project: RuntimeProject, config: RuntimeBuilderConfig) -> None:
    for field in (
        "project_key", "module_type", "source_comfyui_path", "workflow_filename",
        "workflow_json", "container_workdir", "export_root_directory",
        "export_directory", "last_index_summary", "workspace_status",
        "last_export_archive", "last_export_manifest", "last_exported_at",
    ):
        setattr(config, field, getattr(project, field))

@router.get('/config',response_model=RuntimeBuilderConfigResponse)
def read_config(db:Session=Depends(get_db)): return get_or_create(db)
@router.put('/config',response_model=RuntimeBuilderConfigResponse)
def update_config(payload:RuntimeBuilderConfigUpdate,db:Session=Depends(get_db)):
    config=get_or_create(db)
    values = payload.model_dump()
    profile = RuntimeBuilderService.RECOMMENDED_PROFILE
    values.update({
        "python_version": profile["python_version"],
        "cuda_version": profile["cuda_version"],
        "pytorch_index_url": profile["pytorch_index_url"],
        "comfyui_commit": profile["comfyui_commit"],
        "include_comfyui_manager": True,
        "target_platform": "linux/amd64",
        "custom_nodes": RuntimeBuilderService.merge_required_custom_nodes(values.get("custom_nodes")),
    })
    for field,value in values.items(): setattr(config,field,value)
    db.add(config); db.commit(); db.refresh(config); return config
@router.get('/project', response_model=RuntimeProjectResponse)
def read_project(db: Session = Depends(get_db)):
    return get_or_create_project(db)

@router.patch('/project', response_model=RuntimeProjectResponse)
def update_project(payload: RuntimeWorkspaceUpdate, db: Session = Depends(get_db)):
    config = get_or_create(db)
    project = get_or_create_project(db, config)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    sync_project_to_config(project, config)
    db.add_all([project, config]); db.commit(); db.refresh(project)
    return project

@router.patch('/workspace', response_model=RuntimeProjectResponse)
def update_workspace(payload: RuntimeWorkspaceUpdate, db: Session = Depends(get_db)):
    return update_project(payload, db)

@router.post('/validate',response_model=RuntimeValidationResponse)
def validate_config(db:Session=Depends(get_db)): return RuntimeBuilderService.validate(get_or_create(db))
@router.post('/generate',response_model=RuntimeGeneratedFilesResponse)
def generate_files(db:Session=Depends(get_db)): return RuntimeBuilderService.generate(get_or_create(db))
@router.get('/diagnostic',response_model=RuntimeDockerDiagnosticResponse)
def diagnostic(db:Session=Depends(get_db)): return RuntimeBuildExecutionService.diagnostic(db)
@router.get('/builds',response_model=RuntimeBuildListResponse)
def list_builds(limit:int=Query(50,ge=1,le=200),db:Session=Depends(get_db)):
    q=db.query(RuntimeBuilderBuild); return {'items':q.order_by(RuntimeBuilderBuild.id.desc()).limit(limit).all(),'total':q.count()}
@router.post('/builds',response_model=RuntimeBuildResponse)
def create_build(payload:RuntimeBuildCreate,background_tasks:BackgroundTasks,db:Session=Depends(get_db)):
    try: build=RuntimeBuildExecutionService.create(db,get_or_create(db))
    except ValueError as exc: raise HTTPException(422,str(exc))
    background_tasks.add_task(RuntimeBuildExecutionService.start,build.id,payload.push_after_build); return build
@router.get('/builds/{build_id}',response_model=RuntimeBuildResponse)
def read_build(build_id:int,db:Session=Depends(get_db)):
    item=db.get(RuntimeBuilderBuild,build_id)
    if not item: raise HTTPException(404,'Build no encontrado.')
    return item
@router.post('/builds/{build_id}/publish',response_model=RuntimeBuildResponse)
def publish(build_id:int,background_tasks:BackgroundTasks,db:Session=Depends(get_db)):
    item=db.get(RuntimeBuilderBuild,build_id)
    if not item: raise HTTPException(404,'Build no encontrado.')
    background_tasks.add_task(RuntimeBuildExecutionService.publish,item.id); return item
@router.post('/builds/{build_id}/activate',response_model=RuntimeBuildResponse)
def activate(build_id:int,db:Session=Depends(get_db)):
    item=db.get(RuntimeBuilderBuild,build_id)
    if not item: raise HTTPException(404,'Build no encontrado.')
    try: return RuntimeBuildExecutionService.activate(db,item)
    except ValueError as exc: raise HTTPException(422,str(exc))
@router.post('/builds/{build_id}/cancel',response_model=RuntimeBuildResponse)
def cancel(build_id:int,db:Session=Depends(get_db)):
    item=db.get(RuntimeBuilderBuild,build_id)
    if not item: raise HTTPException(404,'Build no encontrado.')
    if item.status in {'building','pending','validating','publishing'}: item.status='cancelled'; item.phase='cancelled'; db.add(item); db.commit(); db.refresh(item)
    return item


@router.post('/builds/bulk-cancel', response_model=RuntimeBuildBulkResponse)
def bulk_cancel_builds(
    payload: RuntimeBuildBulkRequest,
    db: Session = Depends(get_db),
):
    active_statuses = {'building', 'pending', 'validating', 'publishing'}
    items = (
        db.query(RuntimeBuilderBuild)
        .filter(RuntimeBuilderBuild.id.in_(payload.ids))
        .all()
    )
    by_id = {item.id: item for item in items}
    affected_ids: list[int] = []
    skipped_ids: list[int] = []

    for build_id in payload.ids:
        item = by_id.get(build_id)
        if item is None or item.status not in active_statuses:
            skipped_ids.append(build_id)
            continue

        item.status = 'cancelled'
        item.phase = 'cancelled'
        db.add(item)
        affected_ids.append(build_id)

    db.commit()
    return RuntimeBuildBulkResponse(
        affected_ids=affected_ids,
        skipped_ids=skipped_ids,
    )


@router.post('/builds/bulk-delete', response_model=RuntimeBuildBulkResponse)
def bulk_delete_builds(
    payload: RuntimeBuildBulkRequest,
    db: Session = Depends(get_db),
):
    active_statuses = {'building', 'pending', 'validating', 'publishing'}
    items = (
        db.query(RuntimeBuilderBuild)
        .filter(RuntimeBuilderBuild.id.in_(payload.ids))
        .all()
    )
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
    return RuntimeBuildBulkResponse(
        affected_ids=affected_ids,
        skipped_ids=skipped_ids,
    )

@router.post('/import/scan-path')
def import_scan_path(payload:RuntimeImportPathRequest):
    try: return RuntimeImportService.scan_path(payload.path,payload.include_all_models)
    except ValueError as exc: raise HTTPException(422,str(exc))

@router.post('/import/upload')
async def import_upload(file:UploadFile=File(...)):
    if not file.filename or not file.filename.lower().endswith('.zip'): raise HTTPException(422,'Debes cargar un archivo ZIP.')
    content=await file.read()
    if len(content)>100*1024*1024: raise HTTPException(413,'El inventario supera el límite de 100 MB.')
    try: return RuntimeImportService.scan_inventory_zip(content)
    except ValueError as exc: raise HTTPException(422,str(exc))

@router.post('/import/analyze-workflow')
def import_analyze_workflow(payload:RuntimeWorkflowAnalysisRequest):
    return RuntimeImportService.analyze_workflow(payload.workflow,payload.report)

@router.post('/import/apply',response_model=RuntimeBuilderConfigResponse)
def import_apply(payload:RuntimeImportApplyRequest,db:Session=Depends(get_db)):
    return RuntimeImportService.apply_report(db,get_or_create(db),payload.report,payload.selection)

@router.post('/import/resolve-workflow')
def import_resolve_workflow(payload: RuntimeWorkflowResolveRequest, db: Session = Depends(get_db)):
    try:
        result = RuntimeImportService.resolve_workflow(payload.path, payload.workflow)
        config = get_or_create(db)
        project = get_or_create_project(db, config)
        project.source_comfyui_path = payload.path
        project.workflow_json = payload.workflow
        project.workflow_filename = payload.workflow_filename
        project.workspace_status = "workflow_resolved"
        sync_project_to_config(project, config)
        db.add_all([project, config]); db.commit(); db.refresh(project)
        return result
    except ValueError as exc: raise HTTPException(422,str(exc))


@router.post('/intelligence/index')
def intelligence_index(payload: RuntimeIntelligenceIndexRequest, db: Session = Depends(get_db)):
    try:
        result = RuntimeIntelligenceService.build_index(payload.path)
        config = get_or_create(db)
        project = get_or_create_project(db, config)
        project.source_comfyui_path = payload.path
        project.last_index_summary = result.get("summary") or {}
        project.workspace_status = "indexed"
        sync_project_to_config(project, config)
        db.add_all([project, config]); db.commit()
        return result
    except ValueError as exc:
        raise HTTPException(422, str(exc))

@router.post('/intelligence/search')
def intelligence_search(payload: RuntimeIntelligenceSearchRequest):
    try:
        index = RuntimeIntelligenceService.build_index(payload.path)
        return {"items": RuntimeIntelligenceService.search(index, payload.query), "summary": index["summary"]}
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.post('/context/generate', response_model=RuntimeContextJobCreateResponse, status_code=202)
def generate_runtime_context(payload: RuntimeContextGenerateRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    config = get_or_create(db)
    job = RuntimeContextJobService.create(config.id, payload)
    background_tasks.add_task(RuntimeContextJobService.run, job["job_id"])
    return job


@router.get('/context/jobs/{job_id}', response_model=RuntimeContextJobResponse)
def read_runtime_context_job(job_id: str):
    try:
        return RuntimeContextJobService.public(job_id)
    except KeyError:
        raise HTTPException(404, 'Trabajo de exportación no encontrado o el backend fue reiniciado.')


@router.post('/models-volume/analyze')
def analyze_models_volume(payload: RuntimeModelVolumeAnalyzeRequest, db: Session = Depends(get_db)):
    try:
        return RuntimeModelVolumeExportService.analyze(get_or_create(db), payload.comfyui_path)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.post('/models-volume/export', response_model=RuntimeContextJobCreateResponse, status_code=202)
def export_models_volume(payload: RuntimeModelVolumeExportRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    config = get_or_create(db)
    job = RuntimeContextJobService.create_model_volume(config.id, payload)
    background_tasks.add_task(RuntimeContextJobService.run_model_volume, job['job_id'])
    return job
