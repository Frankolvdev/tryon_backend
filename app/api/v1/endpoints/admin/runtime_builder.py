from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session
from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.models.runtime_builder_config import RuntimeBuilderConfig
from app.models.runtime_builder_build import RuntimeBuilderBuild
from app.schemas.runtime_builder import RuntimeBuilderConfigResponse, RuntimeBuilderConfigUpdate, RuntimeGeneratedFilesResponse, RuntimeValidationResponse, RuntimeBuildCreate, RuntimeBuildResponse, RuntimeBuildListResponse, RuntimeDockerDiagnosticResponse, RuntimeImportPathRequest, RuntimeImportApplyRequest, RuntimeWorkflowAnalysisRequest, RuntimeWorkflowResolveRequest, RuntimeIntelligenceIndexRequest, RuntimeIntelligenceSearchRequest
from app.services.runtime_builder_service import RuntimeBuilderService
from app.services.runtime_build_execution_service import RuntimeBuildExecutionService
from app.services.runtime_import_service import RuntimeImportService
from app.services.runtime_intelligence_service import RuntimeIntelligenceService
router=APIRouter(prefix="/runtime-builder",dependencies=[Depends(admin_guard)])

def get_or_create(db):
    config=db.query(RuntimeBuilderConfig).order_by(RuntimeBuilderConfig.id.asc()).first()
    if config is None: config=RuntimeBuilderConfig(); db.add(config); db.commit(); db.refresh(config)
    return config
@router.get('/config',response_model=RuntimeBuilderConfigResponse)
def read_config(db:Session=Depends(get_db)): return get_or_create(db)
@router.put('/config',response_model=RuntimeBuilderConfigResponse)
def update_config(payload:RuntimeBuilderConfigUpdate,db:Session=Depends(get_db)):
    config=get_or_create(db)
    for field,value in payload.model_dump().items(): setattr(config,field,value)
    db.add(config); db.commit(); db.refresh(config); return config
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
def import_resolve_workflow(payload:RuntimeWorkflowResolveRequest, RuntimeIntelligenceIndexRequest, RuntimeIntelligenceSearchRequest):
    try: return RuntimeImportService.resolve_workflow(payload.path,payload.workflow)
    except ValueError as exc: raise HTTPException(422,str(exc))


@router.post('/intelligence/index')
def intelligence_index(payload: RuntimeIntelligenceIndexRequest):
    try:
        return RuntimeIntelligenceService.build_index(payload.path)
    except ValueError as exc:
        raise HTTPException(422, str(exc))

@router.post('/intelligence/search')
def intelligence_search(payload: RuntimeIntelligenceSearchRequest):
    try:
        index = RuntimeIntelligenceService.build_index(payload.path)
        return {"items": RuntimeIntelligenceService.search(index, payload.query), "summary": index["summary"]}
    except ValueError as exc:
        raise HTTPException(422, str(exc))
