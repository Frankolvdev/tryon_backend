from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy import desc, or_
from sqlalchemy.orm import Session

from app.common.time import utc_now
from app.db.database import SessionLocal
from app.models.generation_module_execution import GenerationModuleExecution
from app.schemas.generation_module_runtime import GenerationModuleExecutionResponse, GenerationModuleExecutionLog


class GenerationModuleExecutionStoreService:
    def save(self, execution: GenerationModuleExecutionResponse) -> None:
        db = SessionLocal()
        try:
            row = (
                db.query(GenerationModuleExecution)
                .filter(GenerationModuleExecution.public_id == str(execution.id))
                .first()
            )
            if row is None:
                row = GenerationModuleExecution(
                    public_id=str(execution.id),
                    generation_module_id=execution.module_id,
                    module_key=execution.module_key,
                    user_id=execution.user_id,
                    engine=execution.engine.value if hasattr(execution.engine, "value") else str(execution.engine),
                    status=execution.status,
                    progress=execution.progress,
                    snapshot_json="{}",
                    created_at=execution.created_at,
                )
                db.add(row)
            row.user_id = execution.user_id
            row.engine = execution.engine.value if hasattr(execution.engine, "value") else str(execution.engine)
            row.status = execution.status
            row.progress = execution.progress
            row.snapshot_json = execution.model_dump_json()
            row.error_message = execution.error
            row.started_at = execution.started_at
            row.finished_at = execution.finished_at
            row.updated_at = utc_now()
            db.commit()
        finally:
            db.close()

    @staticmethod
    def _response(row: GenerationModuleExecution) -> GenerationModuleExecutionResponse:
        return GenerationModuleExecutionResponse.model_validate_json(row.snapshot_json)

    def get(self, execution_id: UUID) -> GenerationModuleExecutionResponse | None:
        db = SessionLocal()
        try:
            row = (
                db.query(GenerationModuleExecution)
                .filter(GenerationModuleExecution.public_id == str(execution_id))
                .first()
            )
            if row is None:
                return None
            response = self._response(row)
            if response.status in {"queued", "running"}:
                response.status = "failed"
                response.error = "Execution was interrupted because the backend process restarted. Retry the execution."
                response.finished_at = utc_now()
                response.logs.append(
                    GenerationModuleExecutionLog(
                        timestamp=response.finished_at,
                        level="error",
                        message=response.error,
                    )
                )
                response.duration_ms = (
                    int((response.finished_at - response.started_at).total_seconds() * 1000)
                    if response.started_at else response.duration_ms
                )
                self.save(response)
            return response
        finally:
            db.close()

    def list(
        self,
        *,
        user_id: int | None = None,
        module_id: int | None = None,
        status: str | None = None,
        engine: str | None = None,
        search: str | None = None,
        created_from=None,
        created_to=None,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[GenerationModuleExecutionResponse], int]:
        db = SessionLocal()
        try:
            query = db.query(GenerationModuleExecution)
            if user_id is not None:
                query = query.filter(GenerationModuleExecution.user_id == user_id)
            if module_id is not None:
                query = query.filter(GenerationModuleExecution.generation_module_id == module_id)
            if status:
                query = query.filter(GenerationModuleExecution.status == status)
            if engine:
                query = query.filter(GenerationModuleExecution.engine == engine)
            if created_from is not None:
                query = query.filter(GenerationModuleExecution.created_at >= created_from)
            if created_to is not None:
                query = query.filter(GenerationModuleExecution.created_at <= created_to)
            if search:
                term = f"%{search.strip()}%"
                query = query.filter(or_(
                    GenerationModuleExecution.public_id.ilike(term),
                    GenerationModuleExecution.module_key.ilike(term),
                    GenerationModuleExecution.engine.ilike(term),
                    GenerationModuleExecution.status.ilike(term),
                    GenerationModuleExecution.error_message.ilike(term),
                ))
            total = query.count()
            rows = query.order_by(desc(GenerationModuleExecution.created_at)).offset(skip).limit(limit).all()
            return [self._response(row) for row in rows], total
        finally:
            db.close()

    def delete(self, execution_id: UUID) -> None:
        db = SessionLocal()
        try:
            db.query(GenerationModuleExecution).filter(
                GenerationModuleExecution.public_id == str(execution_id)
            ).delete(synchronize_session=False)
            db.commit()
        finally:
            db.close()


generation_module_execution_store_service = GenerationModuleExecutionStoreService()
