from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.workers.handler_registry import (
    internal_job_handler_registry,
)


class BackgroundJobHandlerItem(BaseModel):
    job_type: str
    execution_mode: str
    registered: bool


class BackgroundJobHandlerListResponse(BaseModel):
    items: list[BackgroundJobHandlerItem]
    total: int


class BackgroundJobHandlerService:
    def list_handlers(
        self,
        db: Session,
    ) -> BackgroundJobHandlerListResponse:
        del db

        names = (
            internal_job_handler_registry
            .list_handler_names()
        )

        return BackgroundJobHandlerListResponse(
            items=[
                BackgroundJobHandlerItem(
                    job_type=name,
                    execution_mode="internal",
                    registered=True,
                )
                for name in names
            ],
            total=len(names),
        )


background_job_handler_service = (
    BackgroundJobHandlerService()
)