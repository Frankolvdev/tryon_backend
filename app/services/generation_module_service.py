import json
from typing import Any

from sqlalchemy.orm import Session

from app.common.exceptions import ConflictException, NotFoundException
from app.models.generation_module import (
    GenerationModule,
    GenerationModuleInput,
    GenerationModuleOutput,
    GenerationModuleStep,
)
from app.repositories.generation_module_repository import generation_module_repository
from app.schemas.generation_module import (
    GenerationModuleCreate,
    GenerationModuleInputDefinition,
    GenerationModuleInputResponse,
    GenerationModuleListResponse,
    GenerationModuleOutputDefinition,
    GenerationModuleOutputResponse,
    GenerationModuleResponse,
    GenerationModuleStepDefinition,
    GenerationModuleStepResponse,
    GenerationModuleUpdate,
)


class GenerationModuleService:
    @staticmethod
    def _serialize(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, default=str)

    @staticmethod
    def _parse(value: str | None, fallback: Any) -> Any:
        if not value:
            return fallback
        try:
            return json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return fallback

    def _input_response(self, item: GenerationModuleInput) -> GenerationModuleInputResponse:
        return GenerationModuleInputResponse(
            id=item.id,
            key=item.key,
            name=item.name,
            description=item.description,
            input_type=item.input_type,
            position=item.position,
            is_required=item.is_required,
            default_value=self._parse(item.default_value_json, None),
            validation=self._parse(item.validation_json, {}),
            created_at=item.created_at,
            updated_at=item.updated_at,
        )

    def _output_response(self, item: GenerationModuleOutput) -> GenerationModuleOutputResponse:
        return GenerationModuleOutputResponse(
            id=item.id,
            key=item.key,
            name=item.name,
            description=item.description,
            output_type=item.output_type,
            position=item.position,
            is_required=item.is_required,
            source_step_key=item.source_step_key,
            source_path=item.source_path,
            metadata=self._parse(item.metadata_json, {}),
            created_at=item.created_at,
            updated_at=item.updated_at,
        )

    def _step_response(self, item: GenerationModuleStep) -> GenerationModuleStepResponse:
        return GenerationModuleStepResponse(
            id=item.id,
            key=item.key,
            name=item.name,
            description=item.description,
            step_type=item.step_type,
            position=item.position,
            is_enabled=item.is_enabled,
            configuration=self._parse(item.configuration_json, {}),
            input_mapping=self._parse(item.input_mapping_json, {}),
            output_mapping=self._parse(item.output_mapping_json, {}),
            created_at=item.created_at,
            updated_at=item.updated_at,
        )

    def _response(self, module: GenerationModule) -> GenerationModuleResponse:
        return GenerationModuleResponse(
            id=module.id,
            key=module.key,
            name=module.name,
            description=module.description,
            version=module.version,
            category=module.category,
            default_execution_engine=module.default_execution_engine,
            metadata=self._parse(module.metadata_json, {}),
            is_active=module.is_active,
            created_by_user_id=module.created_by_user_id,
            inputs=[self._input_response(item) for item in module.inputs],
            outputs=[self._output_response(item) for item in module.outputs],
            steps=[self._step_response(item) for item in module.steps],
            created_at=module.created_at,
            updated_at=module.updated_at,
        )

    @staticmethod
    def _input_model(module_id: int, item: GenerationModuleInputDefinition) -> GenerationModuleInput:
        return GenerationModuleInput(
            generation_module_id=module_id,
            key=item.key,
            name=item.name,
            description=item.description,
            input_type=item.input_type.value,
            position=item.position,
            is_required=item.is_required,
            default_value_json=GenerationModuleService._serialize(item.default_value),
            validation_json=GenerationModuleService._serialize(item.validation),
        )

    @staticmethod
    def _output_model(module_id: int, item: GenerationModuleOutputDefinition) -> GenerationModuleOutput:
        return GenerationModuleOutput(
            generation_module_id=module_id,
            key=item.key,
            name=item.name,
            description=item.description,
            output_type=item.output_type.value,
            position=item.position,
            is_required=item.is_required,
            source_step_key=item.source_step_key,
            source_path=item.source_path,
            metadata_json=GenerationModuleService._serialize(item.metadata),
        )

    @staticmethod
    def _step_model(module_id: int, item: GenerationModuleStepDefinition) -> GenerationModuleStep:
        return GenerationModuleStep(
            generation_module_id=module_id,
            key=item.key,
            name=item.name,
            description=item.description,
            step_type=item.step_type.value,
            position=item.position,
            is_enabled=item.is_enabled,
            configuration_json=GenerationModuleService._serialize(item.configuration),
            input_mapping_json=GenerationModuleService._serialize(item.input_mapping),
            output_mapping_json=GenerationModuleService._serialize(item.output_mapping),
        )

    def get(self, db: Session, *, module_id: int) -> GenerationModule:
        module = generation_module_repository.get_by_id_with_children(db, module_id)
        if not module:
            raise NotFoundException("Generation module not found.")
        return module

    def get_response(self, db: Session, *, module_id: int) -> GenerationModuleResponse:
        return self._response(self.get(db, module_id=module_id))

    def list_modules(
        self,
        db: Session,
        *,
        key: str | None = None,
        category: str | None = None,
        engine: str | None = None,
        is_active: bool | None = None,
        search: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> GenerationModuleListResponse:
        items = generation_module_repository.list_filtered(
            db,
            key=key,
            category=category,
            engine=engine,
            is_active=is_active,
            search=search,
            skip=skip,
            limit=limit,
        )
        total = generation_module_repository.count_filtered(
            db,
            key=key,
            category=category,
            engine=engine,
            is_active=is_active,
            search=search,
        )
        return GenerationModuleListResponse(
            items=[self._response(item) for item in items],
            total=total,
            skip=skip,
            limit=limit,
        )

    def create(
        self,
        db: Session,
        *,
        data: GenerationModuleCreate,
        created_by_user_id: int | None,
    ) -> GenerationModuleResponse:
        existing = generation_module_repository.get_by_key_and_version(
            db, key=data.key, version=data.version
        )
        if existing:
            raise ConflictException("A generation module with this key and version already exists.")

        module = GenerationModule(
            key=data.key,
            name=data.name,
            description=data.description,
            version=data.version,
            category=data.category,
            default_execution_engine=data.default_execution_engine.value,
            metadata_json=self._serialize(data.metadata),
            is_active=data.is_active,
            created_by_user_id=created_by_user_id,
        )
        db.add(module)
        db.flush()
        module.inputs = [self._input_model(module.id, item) for item in data.inputs]
        module.outputs = [self._output_model(module.id, item) for item in data.outputs]
        module.steps = [self._step_model(module.id, item) for item in data.steps]
        db.commit()
        return self.get_response(db, module_id=module.id)

    def update(
        self,
        db: Session,
        *,
        module_id: int,
        data: GenerationModuleUpdate,
    ) -> GenerationModuleResponse:
        module = self.get(db, module_id=module_id)
        payload = data.model_dump(exclude_unset=True)

        for field in ("name", "description", "category", "is_active"):
            if field in payload:
                setattr(module, field, payload[field])
        if (
            "default_execution_engine" in payload
            and data.default_execution_engine is not None
        ):
            module.default_execution_engine = data.default_execution_engine.value
        if "metadata" in payload:
            module.metadata_json = self._serialize(data.metadata)
        if data.inputs is not None:
            module.inputs.clear()
            db.flush()
            module.inputs = [self._input_model(module.id, item) for item in data.inputs]
        if data.outputs is not None:
            module.outputs.clear()
            db.flush()
            module.outputs = [self._output_model(module.id, item) for item in data.outputs]
        if data.steps is not None:
            module.steps.clear()
            db.flush()
            module.steps = [self._step_model(module.id, item) for item in data.steps]

        db.add(module)
        db.commit()
        return self.get_response(db, module_id=module.id)

    def delete(self, db: Session, *, module_id: int) -> None:
        module = self.get(db, module_id=module_id)
        db.delete(module)
        db.commit()


generation_module_service = GenerationModuleService()
