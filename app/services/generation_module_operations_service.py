from __future__ import annotations

from sqlalchemy.orm import Session

from app.common.exceptions import ConflictException, NotFoundException
from app.models.generation_module import GenerationModule
from app.schemas.generation_module import GenerationModuleCreate
from app.schemas.generation_module_operations import (
    GenerationModuleCloneRequest,
    GenerationModuleExportResponse,
    GenerationModuleImportRequest,
    GenerationModulePublishRequest,
    GenerationModuleVersionListResponse,
)
from app.services.generation_module_service import generation_module_service


class GenerationModuleOperationsService:
    def list_versions(self, db: Session, *, module_id: int) -> GenerationModuleVersionListResponse:
        module = generation_module_service.get(db, module_id=module_id)
        rows = (
            db.query(GenerationModule)
            .filter(GenerationModule.key == module.key)
            .order_by(GenerationModule.version.desc())
            .all()
        )
        return GenerationModuleVersionListResponse(
            items=[generation_module_service._response(row) for row in rows],
            total=len(rows),
        )

    def clone(self, db: Session, *, module_id: int, data: GenerationModuleCloneRequest, user_id: int | None):
        source = generation_module_service.get_response(db, module_id=module_id)
        max_version = (
            db.query(GenerationModule.version)
            .filter(GenerationModule.key == source.key)
            .order_by(GenerationModule.version.desc())
            .first()
        )
        next_version = (max_version[0] if max_version else source.version) + 1
        payload = GenerationModuleCreate(
            key=source.key,
            name=data.name or source.name,
            description=source.description,
            version=next_version,
            category=source.category,
            default_execution_engine=source.default_execution_engine,
            metadata={**source.metadata, "cloned_from_module_id": source.id},
            is_active=data.activate,
            inputs=[item.model_dump(exclude={"id", "created_at", "updated_at"}) for item in source.inputs],
            outputs=[item.model_dump(exclude={"id", "created_at", "updated_at"}) for item in source.outputs],
            steps=[item.model_dump(exclude={"id", "created_at", "updated_at"}) for item in source.steps],
        )
        return generation_module_service.create(db, data=payload, created_by_user_id=user_id)

    def publish(self, db: Session, *, module_id: int, data: GenerationModulePublishRequest):
        module = generation_module_service.get(db, module_id=module_id)
        if data.deactivate_other_versions:
            (
                db.query(GenerationModule)
                .filter(GenerationModule.key == module.key, GenerationModule.id != module.id)
                .update({GenerationModule.is_active: False}, synchronize_session=False)
            )
        module.is_active = True
        db.add(module)
        db.commit()
        return generation_module_service.get_response(db, module_id=module.id)

    def export(self, db: Session, *, module_id: int) -> GenerationModuleExportResponse:
        module = generation_module_service.get_response(db, module_id=module_id)
        payload = {
            "key": module.key,
            "name": module.name,
            "description": module.description,
            "version": module.version,
            "category": module.category,
            "default_execution_engine": module.default_execution_engine.value,
            "metadata": module.metadata,
            "is_active": module.is_active,
            "inputs": [item.model_dump(mode="json", exclude={"id", "created_at", "updated_at"}) for item in module.inputs],
            "outputs": [item.model_dump(mode="json", exclude={"id", "created_at", "updated_at"}) for item in module.outputs],
            "steps": [item.model_dump(mode="json", exclude={"id", "created_at", "updated_at"}) for item in module.steps],
        }
        return GenerationModuleExportResponse(module=payload)

    def import_module(self, db: Session, *, data: GenerationModuleImportRequest, user_id: int | None):
        existing = (
            db.query(GenerationModule)
            .filter(GenerationModule.key == data.module.key, GenerationModule.version == data.module.version)
            .first()
        )
        if existing and not data.replace_existing:
            raise ConflictException("A generation module with this key and version already exists.")
        if existing:
            db.delete(existing)
            db.commit()
        return generation_module_service.create(db, data=data.module, created_by_user_id=user_id)


generation_module_operations_service = GenerationModuleOperationsService()
