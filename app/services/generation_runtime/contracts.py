from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from sqlalchemy.orm import Session

from app.common.generation_module_enums import GenerationExecutionEngine


class GenerationRuntimeStepHost(Protocol):
    """Host operations required by the provider-neutral step registry."""

    def execute_workflow_step(
        self,
        db: Session,
        execution_id: UUID,
        step: dict[str, Any],
        context: dict[str, Any],
        engine: GenerationExecutionEngine,
    ) -> dict[str, Any]: ...

    def execute_python_step(
        self,
        db: Session,
        execution_id: UUID,
        step: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]: ...
