from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.common.exceptions import AppException
from app.common.generation_module_enums import GenerationExecutionEngine, GenerationModuleStepType
from app.services.generation_runtime.contracts import GenerationRuntimeStepHost


class GenerationRuntimeStepRegistry:
    """Strict dispatcher for the two currently supported runtime step types."""

    def __init__(self, host: GenerationRuntimeStepHost) -> None:
        self._host = host

    def execute(
        self,
        db: Session,
        execution_id: UUID,
        step: dict[str, Any],
        context: dict[str, Any],
        engine: GenerationExecutionEngine,
    ) -> dict[str, Any]:
        step_type = step.get("step_type")
        if step_type == GenerationModuleStepType.WORKFLOW.value:
            return self._host.execute_workflow_step(db, execution_id, step, context, engine)
        if step_type == GenerationModuleStepType.PYTHON.value:
            return self._host.execute_python_step(db, execution_id, step, context)
        raise AppException(f"Unsupported generation module step type: {step_type}")
