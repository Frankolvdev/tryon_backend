import ast
import json
from typing import Any

from sqlalchemy.orm import Session

from app.common.exceptions import AppException, ConflictException, NotFoundException
from app.common.generation_module_enums import GenerationModuleStepType
from app.models.generation_module import GenerationModule, GenerationModuleStep
from app.schemas.generation_module import GenerationModuleResponse
from app.schemas.generation_module_authoring import (
    GenerationModuleStepsReorderRequest,
    PythonStepCreateRequest,
    PythonStepUpdateRequest,
    WorkflowInputBinding,
    WorkflowOutputBinding,
    WorkflowStepBindingsUpdate,
    WorkflowStepUpdateRequest,
    WorkflowStepImportRequest,
    WorkflowValidationResponse,
)
from app.services.generation_module_service import generation_module_service


class GenerationModuleAuthoringService:
    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, default=str)

    @staticmethod
    def _load(value: str | None, fallback: Any) -> Any:
        if not value:
            return fallback
        try:
            return json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return fallback

    @staticmethod
    def _node_map(workflow_json: dict[str, Any]) -> dict[str, dict[str, Any]]:
        nodes: dict[str, dict[str, Any]] = {}
        for raw_node_id, raw_node in workflow_json.items():
            node_id = str(raw_node_id)
            if not isinstance(raw_node, dict):
                raise AppException(f"Workflow node '{node_id}' must be a JSON object.")
            if not isinstance(raw_node.get("class_type"), str) or not raw_node["class_type"].strip():
                raise AppException(f"Workflow node '{node_id}' has no valid class_type.")
            inputs = raw_node.get("inputs")
            if inputs is None:
                raw_node["inputs"] = {}
            elif not isinstance(inputs, dict):
                raise AppException(f"Workflow node '{node_id}' inputs must be a JSON object.")
            nodes[node_id] = raw_node
        if not nodes:
            raise AppException("The ComfyUI workflow cannot be empty.")
        return nodes

    def validate_workflow(self, workflow_json: dict[str, Any]) -> WorkflowValidationResponse:
        nodes = self._node_map(workflow_json)
        return WorkflowValidationResponse(
            valid=True,
            node_count=len(nodes),
            node_ids=list(nodes.keys()),
            class_types=sorted({node["class_type"] for node in nodes.values()}),
        )

    @staticmethod
    def _step(module: GenerationModule, step_id: int) -> GenerationModuleStep:
        step = next((item for item in module.steps if item.id == step_id), None)
        if not step:
            raise NotFoundException("Generation module step not found.")
        return step

    @staticmethod
    def _assert_step_identity_available(
        module: GenerationModule,
        *,
        key: str,
        position: int,
        ignore_step_id: int | None = None,
    ) -> None:
        if any(item.key == key and item.id != ignore_step_id for item in module.steps):
            raise ConflictException("A step with this key already exists in the module.")
        if any(item.position == position and item.id != ignore_step_id for item in module.steps):
            raise ConflictException("A step already uses this position in the module.")


    @staticmethod
    def _dedupe_input_bindings(
        bindings: list[WorkflowInputBinding],
    ) -> list[WorkflowInputBinding]:
        """Keep only the latest binding for each logical workflow input port."""
        deduped: dict[tuple[str, ...], WorkflowInputBinding] = {}
        order: list[tuple[str, ...]] = []
        for binding in bindings:
            key = (
                ("port", binding.port_id)
                if binding.port_id
                else ("target", str(binding.node_id), binding.input_field)
            )
            if key not in deduped:
                order.append(key)
            deduped[key] = binding
        return [deduped[key] for key in order]

    @staticmethod
    def _assert_bindings(
        module: GenerationModule,
        nodes: dict[str, dict[str, Any]],
        input_bindings: list[WorkflowInputBinding],
        output_bindings: list[WorkflowOutputBinding],
    ) -> None:
        module_input_keys = {item.key for item in module.inputs}
        module_output_keys = {item.key for item in module.outputs}

        for binding in input_bindings:
            if binding.module_input_key and binding.module_input_key not in module_input_keys:
                raise AppException(
                    f"Module input '{binding.module_input_key}' does not exist."
                )
            node = nodes.get(str(binding.node_id))
            if not node:
                raise AppException(f"Workflow node '{binding.node_id}' does not exist.")
            if binding.input_field not in node.get("inputs", {}):
                raise AppException(
                    f"Input field '{binding.input_field}' does not exist in workflow node '{binding.node_id}'."
                )

        for binding in output_bindings:
            if binding.module_output_key not in module_output_keys:
                raise AppException(
                    f"Module output '{binding.module_output_key}' does not exist."
                )
            if str(binding.node_id) not in nodes:
                raise AppException(f"Workflow node '{binding.node_id}' does not exist.")

    def import_workflow_step(
        self,
        db: Session,
        *,
        module_id: int,
        data: WorkflowStepImportRequest,
    ) -> GenerationModuleResponse:
        module = generation_module_service.get(db, module_id=module_id)
        self._assert_step_identity_available(
            module, key=data.key, position=data.position
        )
        nodes = self._node_map(data.workflow_json)
        input_bindings = self._dedupe_input_bindings(data.input_bindings)
        self._assert_bindings(
            module, nodes, input_bindings, data.output_bindings
        )
        configuration = {
            "workflow_name": data.workflow_name,
            "workflow": data.workflow_json,
            "input_bindings": [item.model_dump() for item in input_bindings],
            "output_bindings": [item.model_dump() for item in data.output_bindings],
        }
        db.add(
            GenerationModuleStep(
                generation_module_id=module.id,
                key=data.key,
                name=data.name,
                description=data.description,
                step_type=GenerationModuleStepType.WORKFLOW.value,
                position=data.position,
                is_enabled=data.is_enabled,
                configuration_json=self._json(configuration),
                input_mapping_json="{}",
                output_mapping_json="{}",
            )
        )
        db.commit()
        return generation_module_service.get_response(db, module_id=module.id)

    def update_workflow_step(
        self,
        db: Session,
        *,
        module_id: int,
        step_id: int,
        data: WorkflowStepUpdateRequest,
    ) -> GenerationModuleResponse:
        module = generation_module_service.get(db, module_id=module_id)
        step = self._step(module, step_id)
        if step.step_type != GenerationModuleStepType.WORKFLOW.value:
            raise AppException("The selected step is not a workflow step.")

        configuration = self._load(step.configuration_json, {})
        workflow_json = data.workflow_json if data.workflow_json is not None else configuration.get("workflow")
        if not isinstance(workflow_json, dict) or not workflow_json:
            raise AppException("The workflow step has no valid workflow JSON.")

        input_bindings = data.input_bindings
        if input_bindings is None:
            input_bindings = [WorkflowInputBinding(**item) for item in configuration.get("input_bindings", [])]
        output_bindings = data.output_bindings
        if output_bindings is None:
            output_bindings = [WorkflowOutputBinding(**item) for item in configuration.get("output_bindings", [])]

        input_bindings = self._dedupe_input_bindings(input_bindings)
        nodes = self._node_map(workflow_json)
        self._assert_bindings(module, nodes, input_bindings, output_bindings)

        if data.name is not None:
            step.name = data.name
        if "description" in data.model_fields_set:
            step.description = data.description
        if data.is_enabled is not None:
            step.is_enabled = data.is_enabled
        if "workflow_name" in data.model_fields_set:
            configuration["workflow_name"] = data.workflow_name
        configuration["workflow"] = workflow_json
        configuration["input_bindings"] = [item.model_dump() for item in input_bindings]
        configuration["output_bindings"] = [item.model_dump() for item in output_bindings]
        step.configuration_json = self._json(configuration)
        db.add(step)
        db.commit()
        return generation_module_service.get_response(db, module_id=module.id)

    def update_workflow_bindings(
        self,
        db: Session,
        *,
        module_id: int,
        step_id: int,
        data: WorkflowStepBindingsUpdate,
    ) -> GenerationModuleResponse:
        module = generation_module_service.get(db, module_id=module_id)
        step = self._step(module, step_id)
        if step.step_type != GenerationModuleStepType.WORKFLOW.value:
            raise AppException("The selected step is not a workflow step.")
        configuration = self._load(step.configuration_json, {})
        workflow_json = configuration.get("workflow")
        if not isinstance(workflow_json, dict):
            raise AppException("The workflow step has no valid workflow JSON.")
        nodes = self._node_map(workflow_json)
        input_bindings = self._dedupe_input_bindings(data.input_bindings)
        self._assert_bindings(module, nodes, input_bindings, data.output_bindings)
        configuration["input_bindings"] = [item.model_dump() for item in input_bindings]
        configuration["output_bindings"] = [item.model_dump() for item in data.output_bindings]
        step.configuration_json = self._json(configuration)
        db.add(step)
        db.commit()
        return generation_module_service.get_response(db, module_id=module.id)

    def create_python_step(
        self,
        db: Session,
        *,
        module_id: int,
        data: PythonStepCreateRequest,
    ) -> GenerationModuleResponse:
        module = generation_module_service.get(db, module_id=module_id)
        self._assert_step_identity_available(module, key=data.key, position=data.position)
        self._validate_python_source(data.source_code, data.entrypoint)
        configuration = {
            "source_code": data.source_code,
            "entrypoint": data.entrypoint,
            "timeout_seconds": data.timeout_seconds,
        }
        db.add(
            GenerationModuleStep(
                generation_module_id=module.id,
                key=data.key,
                name=data.name,
                description=data.description,
                step_type=GenerationModuleStepType.PYTHON.value,
                position=data.position,
                is_enabled=data.is_enabled,
                configuration_json=self._json(configuration),
                input_mapping_json=self._json(data.input_mapping),
                output_mapping_json=self._json(data.output_mapping),
            )
        )
        db.commit()
        return generation_module_service.get_response(db, module_id=module.id)

    def update_python_step(
        self,
        db: Session,
        *,
        module_id: int,
        step_id: int,
        data: PythonStepUpdateRequest,
    ) -> GenerationModuleResponse:
        module = generation_module_service.get(db, module_id=module_id)
        step = self._step(module, step_id)
        if step.step_type != GenerationModuleStepType.PYTHON.value:
            raise AppException("The selected step is not a Python step.")
        configuration = self._load(step.configuration_json, {})
        source_code = data.source_code if data.source_code is not None else configuration.get("source_code", "")
        entrypoint = data.entrypoint if data.entrypoint is not None else configuration.get("entrypoint", "run")
        self._validate_python_source(source_code, entrypoint)

        if data.name is not None:
            step.name = data.name
        if "description" in data.model_fields_set:
            step.description = data.description
        if data.is_enabled is not None:
            step.is_enabled = data.is_enabled
        configuration["source_code"] = source_code
        configuration["entrypoint"] = entrypoint
        if data.timeout_seconds is not None:
            configuration["timeout_seconds"] = data.timeout_seconds
        step.configuration_json = self._json(configuration)
        if data.input_mapping is not None:
            step.input_mapping_json = self._json(data.input_mapping)
        if data.output_mapping is not None:
            step.output_mapping_json = self._json(data.output_mapping)
        db.add(step)
        db.commit()
        return generation_module_service.get_response(db, module_id=module.id)

    @staticmethod
    def _validate_python_source(source_code: str, entrypoint: str) -> None:
        try:
            tree = ast.parse(source_code)
        except SyntaxError as exc:
            raise AppException(
                f"Python syntax error on line {exc.lineno}: {exc.msg}."
            ) from exc
        functions = {
            node.name
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        if entrypoint not in functions:
            raise AppException(
                f"Python entrypoint '{entrypoint}' was not found in the source code."
            )

    def reorder_steps(
        self,
        db: Session,
        *,
        module_id: int,
        data: GenerationModuleStepsReorderRequest,
    ) -> GenerationModuleResponse:
        module = generation_module_service.get(db, module_id=module_id)
        module_step_ids = {item.id for item in module.steps}
        request_ids = {item.step_id for item in data.items}
        if request_ids != module_step_ids:
            raise AppException(
                "Reordering must include every step in the generation module exactly once."
            )
        # Move to temporary negative positions first to satisfy the unique index.
        for index, step in enumerate(module.steps, start=1):
            step.position = -index
            db.add(step)
        db.flush()
        target_positions = {item.step_id: item.position for item in data.items}
        for step in module.steps:
            step.position = target_positions[step.id]
            db.add(step)
        db.commit()
        return generation_module_service.get_response(db, module_id=module.id)

    def delete_step(
        self,
        db: Session,
        *,
        module_id: int,
        step_id: int,
    ) -> GenerationModuleResponse:
        module = generation_module_service.get(db, module_id=module_id)
        step = self._step(module, step_id)
        db.delete(step)
        db.commit()
        return generation_module_service.get_response(db, module_id=module.id)


generation_module_authoring_service = GenerationModuleAuthoringService()
