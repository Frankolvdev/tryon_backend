import json
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.exceptions import ConflictException, NotFoundException
from app.models.generation_module import (
    GenerationModule,
    GenerationModuleInput,
    GenerationModuleOutput,
    GenerationModuleStep,
)
from app.models.generation_module_execution import GenerationModuleExecution
from app.repositories.generation_module_repository import generation_module_repository
from app.repositories.pricing_rule_repository import pricing_rule_repository
from app.services.pricing_service import pricing_service
from app.schemas.generation_module import (
    GenerationModuleCreate,
    GenerationModuleInputDefinition,
    GenerationModuleInputResponse,
    GenerationModuleListResponse,
    GenerationModulePricingResponse,
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
        configuration = self._parse(item.configuration_json, {})
        output_mapping = self._parse(item.output_mapping_json, {})
        if item.step_type == "utility":
            input_ports = configuration.get("input_ports") or []
            if isinstance(input_ports, list):
                mirrored_ports = [dict(port) for port in input_ports if isinstance(port, dict)]
                configuration["output_ports"] = mirrored_ports
                configuration["passthrough_mode"] = "mirror_inputs"
                output_mapping = {
                    str(port.get("id")): str(port.get("id"))
                    for port in mirrored_ports
                    if port.get("id")
                }
        return GenerationModuleStepResponse(
            id=item.id,
            key=item.key,
            name=item.name,
            description=item.description,
            step_type=item.step_type,
            position=item.position,
            is_enabled=item.is_enabled,
            configuration=configuration,
            input_mapping=self._parse(item.input_mapping_json, {}),
            output_mapping=output_mapping,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )

    def _response(self, db: Session, module: GenerationModule) -> GenerationModuleResponse:
        rule = pricing_rule_repository.get_for_generation_module(db, module.id)
        pricing = None
        if rule is not None:
            quote = pricing_service._to_response(db, rule)
            applied = pricing_service.get_applied_rule_for_module(db, module.id)
            pricing = GenerationModulePricingResponse(
                id=quote.id, required_tokens=(applied.estimated_tokens if applied and applied.estimated_tokens is not None else quote.required_tokens),
                final_price_usd=(applied.estimated_final_price_usd if applied and applied.estimated_final_price_usd is not None else quote.final_price_usd),
                token_value_usd=quote.token_value_usd, currency=quote.currency, is_active=quote.is_active,
                estimated_duration_seconds=(applied.estimated_duration_seconds if applied else quote.initial_estimated_duration_seconds),
                estimated_duration_source=(applied.estimate_source if applied else "initial"),
                historical_samples_used=(applied.historical_samples_used if applied else 0),
                estimate_confidence=(applied.estimate_confidence if applied else "low"),
                estimate_updated_at=(applied.estimate_updated_at if applied else None),
                estimated_billable_seconds=(applied.estimated_billable_seconds if applied else None),
                provider=(applied.provider if applied else module.default_execution_engine),
                gpu_key=(applied.gpu_key if applied else None),
            )
        return GenerationModuleResponse(
            id=module.id,
            key=module.key,
            name=module.name,
            description=module.description,
            version=module.version,
            category=module.category,
            endpoint=module.endpoint,
            default_execution_engine=module.default_execution_engine,
            metadata=self._parse(module.metadata_json, {}),
            is_active=module.is_active,
            created_by_user_id=module.created_by_user_id,
            pricing_rule_id=rule.id if rule else None,
            pricing=pricing,
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
        return self._response(db, self.get(db, module_id=module_id))

    def _bind_pricing_rule(self, db: Session, *, module_id: int, pricing_rule_id: int | None) -> None:
        module = generation_module_repository.get_by_id(db, module_id)
        if module is None:
            raise NotFoundException("Generation module not found.")

        if pricing_rule_id is None:
            module.pricing_rule_id = None
            module.is_active = False
            db.add(module)
            return

        selected = pricing_rule_repository.get_by_id(db, pricing_rule_id)
        if not selected:
            raise NotFoundException("Pricing rule not found.")

        # Pricing rules are reusable catalog entries. The assignment belongs to
        # the generation module; assigning the same rule to another module must
        # never clone or move the pricing rule.
        module.pricing_rule_id = selected.id
        db.add(module)

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
        response_items = [self._response(db, item) for item in items]
        return GenerationModuleListResponse(
            items=response_items,
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
            endpoint=(data.endpoint.strip() if data.endpoint else None),
            default_execution_engine=(
                data.default_execution_engine.value
                if data.default_execution_engine is not None
                else None
            ),
            metadata_json=self._serialize(data.metadata),
            is_active=(
                data.is_active
                and data.pricing_rule_id is not None
                and data.default_execution_engine is not None
            ),
            created_by_user_id=created_by_user_id,
        )
        db.add(module)
        db.flush()
        module.inputs = [self._input_model(module.id, item) for item in data.inputs]
        module.outputs = [self._output_model(module.id, item) for item in data.outputs]
        module.steps = [self._step_model(module.id, item) for item in data.steps]
        self._bind_pricing_rule(db, module_id=module.id, pricing_rule_id=data.pricing_rule_id)
        db.flush()
        from app.services.financial_protection_service import financial_protection_service
        financial_protection_service.assert_report_safe(
            financial_protection_service.report(db), action="create generation module"
        )
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

        for field in ("name", "description", "category", "endpoint", "is_active"):
            if field in payload:
                setattr(module, field, payload[field])
        if "default_execution_engine" in payload:
            module.default_execution_engine = (
                data.default_execution_engine.value
                if data.default_execution_engine is not None
                else None
            )
            # A module without an execution engine is a draft. Keep it safely
            # inactive until the administrator completes its configuration.
            if data.default_execution_engine is None:
                module.is_active = False
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
        if "pricing_rule_id" in data.model_fields_set:
            self._bind_pricing_rule(db, module_id=module.id, pricing_rule_id=data.pricing_rule_id)
        if data.steps is not None:
            module.steps.clear()
            db.flush()
            module.steps = [self._step_model(module.id, item) for item in data.steps]

        db.add(module)
        db.flush()
        from app.services.financial_protection_service import financial_protection_service
        financial_protection_service.assert_report_safe(
            financial_protection_service.report(db), action="update generation module"
        )
        db.commit()
        return self.get_response(db, module_id=module.id)

    def delete(self, db: Session, *, module_id: int) -> None:
        module = self.get(db, module_id=module_id)

        # generation_module_executions uses ON DELETE CASCADE. A hard delete of
        # a module with history would therefore erase operational evidence and
        # can indirectly damage financial/audit traceability. Only pristine,
        # never-executed modules may be physically removed.
        execution_count = int(
            db.scalar(
                select(func.count(GenerationModuleExecution.id)).where(
                    GenerationModuleExecution.generation_module_id == module_id
                )
            )
            or 0
        )
        if execution_count:
            raise ConflictException(
                "This module already has execution history and cannot be deleted. "
                "Deactivate it instead to preserve generation and financial history."
            )

        db.delete(module)
        db.commit()


generation_module_service = GenerationModuleService()
