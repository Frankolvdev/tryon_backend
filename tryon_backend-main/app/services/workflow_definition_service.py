import json
from typing import Any

from sqlalchemy.orm import Session

from app.common.exceptions import (
    ConflictException,
    NotFoundException,
)
from app.models.workflow_definition import (
    WorkflowDefinition,
)
from app.repositories.workflow_definition_repository import (
    workflow_definition_repository,
)
from app.schemas.workflow_definition import (
    WorkflowDefinitionCreate,
    WorkflowDefinitionListResponse,
    WorkflowDefinitionResponse,
    WorkflowDefinitionUpdate,
    WorkflowVersionCreate,
)
from app.services.cache_invalidation_service import (
    cache_invalidation_service,
)
from app.services.reference_data_cache_service import (
    reference_data_cache_service,
)


class WorkflowDefinitionService:
    def _serialize(
        self,
        value: Any,
    ) -> str:
        return json.dumps(
            value or {},
            ensure_ascii=False,
            default=str,
        )

    def _parse_dict(
        self,
        value: str | None,
    ) -> dict[str, Any]:
        if not value:
            return {}

        try:
            parsed = json.loads(value)

            return (
                parsed
                if isinstance(parsed, dict)
                else {}
            )

        except (
            TypeError,
            json.JSONDecodeError,
        ):
            return {}

    def _parse_list(
        self,
        value: str | None,
    ) -> list[str]:
        if not value:
            return []

        try:
            parsed = json.loads(value)

            if not isinstance(parsed, list):
                return []

            return [
                str(item)
                for item in parsed
            ]

        except (
            TypeError,
            json.JSONDecodeError,
        ):
            return []

    def _response(
        self,
        workflow: WorkflowDefinition,
    ) -> WorkflowDefinitionResponse:
        return WorkflowDefinitionResponse(
            id=workflow.id,
            key=workflow.key,
            name=workflow.name,
            description=workflow.description,
            version=workflow.version,
            category=workflow.category,
            workflow=self._parse_dict(
                workflow.workflow_json
            ),
            parameter_schema=self._parse_dict(
                workflow.parameter_schema_json
            ),
            execution_modes=self._parse_list(
                workflow.execution_modes_json
            ),
            metadata=self._parse_dict(
                workflow.metadata_json
            ),
            is_active=workflow.is_active,
            is_default=workflow.is_default,
            created_by_user_id=(
                workflow.created_by_user_id
            ),
            created_at=workflow.created_at,
            updated_at=workflow.updated_at,
        )

    def _get_uncached(
        self,
        db: Session,
        *,
        workflow_id: int,
    ) -> WorkflowDefinition | None:
        return (
            workflow_definition_repository
            .get_by_id(
                db,
                workflow_id,
            )
        )

    def get(
        self,
        db: Session,
        *,
        workflow_id: int,
    ) -> WorkflowDefinition:
        workflow = self._get_uncached(
            db,
            workflow_id=workflow_id,
        )

        if not workflow:
            raise NotFoundException(
                "Workflow definition not found."
            )

        return workflow

    def get_response(
        self,
        db: Session,
        *,
        workflow_id: int,
    ) -> WorkflowDefinitionResponse:
        cached_value = (
            reference_data_cache_service
            .remember_workflow(
                workflow_id=workflow_id,
                loader=lambda: (
                    self._response(workflow)
                    if (
                        workflow := (
                            self._get_uncached(
                                db,
                                workflow_id=(
                                    workflow_id
                                ),
                            )
                        )
                    )
                    else None
                ),
            )
        )

        if cached_value is None:
            raise NotFoundException(
                "Workflow definition not found."
            )

        return WorkflowDefinitionResponse(
            **cached_value
        )

    def list_workflows(
        self,
        db: Session,
        *,
        key: str | None = None,
        category: str | None = None,
        is_active: bool | None = None,
        is_default: bool | None = None,
        search: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> WorkflowDefinitionListResponse:
        filters = {
            "key": key,
            "category": category,
            "is_active": is_active,
            "is_default": is_default,
            "search": search,
            "skip": skip,
            "limit": limit,
        }

        def loader():
            items = (
                workflow_definition_repository
                .list_filtered(
                    db,
                    key=key,
                    category=category,
                    is_active=is_active,
                    is_default=is_default,
                    search=search,
                    skip=skip,
                    limit=limit,
                )
            )

            total = (
                workflow_definition_repository
                .count_filtered(
                    db,
                    key=key,
                    category=category,
                    is_active=is_active,
                    is_default=is_default,
                    search=search,
                )
            )

            return {
                "items": [
                    self._response(item)
                    .model_dump(
                        mode="json"
                    )
                    for item in items
                ],
                "total": total,
                "skip": skip,
                "limit": limit,
            }

        cached_value = (
            reference_data_cache_service
            .remember_workflow_list(
                filters=filters,
                loader=loader,
            )
        )

        return WorkflowDefinitionListResponse(
            **cached_value
        )

    def _clear_category_defaults(
        self,
        db: Session,
        *,
        category: str,
        except_id: int | None = None,
    ) -> None:
        defaults = (
            workflow_definition_repository
            .list_defaults_for_category(
                db,
                category=category,
            )
        )

        for item in defaults:
            if (
                except_id is not None
                and item.id == except_id
            ):
                continue

            item.is_default = False
            db.add(item)

    def create(
        self,
        db: Session,
        *,
        data: WorkflowDefinitionCreate,
        created_by_user_id: int | None,
    ) -> WorkflowDefinitionResponse:
        existing = (
            workflow_definition_repository
            .get_by_key_and_version(
                db,
                key=data.key,
                version=data.version,
            )
        )

        if existing:
            raise ConflictException(
                "This workflow key and version "
                "already exist."
            )

        if data.is_default:
            self._clear_category_defaults(
                db,
                category=data.category,
            )

        workflow = WorkflowDefinition(
            key=data.key,
            name=data.name,
            description=data.description,
            version=data.version,
            category=data.category,
            workflow_json=self._serialize(
                data.workflow
            ),
            parameter_schema_json=self._serialize(
                data.parameter_schema
            ),
            execution_modes_json=self._serialize(
                [
                    item.value
                    for item in data.execution_modes
                ]
            ),
            metadata_json=self._serialize(
                data.metadata
            ),
            is_active=data.is_active,
            is_default=data.is_default,
            created_by_user_id=(
                created_by_user_id
            ),
        )

        db.add(workflow)
        db.commit()
        db.refresh(workflow)

        cache_invalidation_service.invalidate_workflows(
            workflow_id=workflow.id,
            workflow_key=workflow.key,
            category=workflow.category,
        )

        return self._response(workflow)

    def update(
        self,
        db: Session,
        *,
        workflow_id: int,
        data: WorkflowDefinitionUpdate,
    ) -> WorkflowDefinitionResponse:
        workflow = self.get(
            db,
            workflow_id=workflow_id,
        )

        old_key = workflow.key
        old_category = workflow.category

        if data.name is not None:
            workflow.name = data.name

        if data.description is not None:
            workflow.description = (
                data.description
            )

        if data.category is not None:
            workflow.category = data.category

        if data.workflow is not None:
            workflow.workflow_json = (
                self._serialize(
                    data.workflow
                )
            )

        if data.parameter_schema is not None:
            workflow.parameter_schema_json = (
                self._serialize(
                    data.parameter_schema
                )
            )

        if data.execution_modes is not None:
            workflow.execution_modes_json = (
                self._serialize(
                    [
                        item.value
                        for item
                        in data.execution_modes
                    ]
                )
            )

        if data.metadata is not None:
            workflow.metadata_json = (
                self._serialize(
                    data.metadata
                )
            )

        if data.is_active is not None:
            workflow.is_active = (
                data.is_active
            )

        if data.is_default is not None:
            if data.is_default:
                self._clear_category_defaults(
                    db,
                    category=workflow.category,
                    except_id=workflow.id,
                )

            workflow.is_default = (
                data.is_default
            )

        db.add(workflow)
        db.commit()
        db.refresh(workflow)

        cache_invalidation_service.invalidate_workflows(
            workflow_id=workflow.id,
            workflow_key=old_key,
            category=old_category,
        )

        cache_invalidation_service.invalidate_workflows(
            workflow_id=workflow.id,
            workflow_key=workflow.key,
            category=workflow.category,
        )

        return self._response(workflow)

    def create_version(
        self,
        db: Session,
        *,
        workflow_id: int,
        data: WorkflowVersionCreate,
        created_by_user_id: int | None,
    ) -> WorkflowDefinitionResponse:
        source = self.get(
            db,
            workflow_id=workflow_id,
        )

        latest = (
            workflow_definition_repository
            .get_latest_by_key(
                db,
                key=source.key,
            )
        )

        next_version = (
            latest.version + 1
            if latest
            else source.version + 1
        )

        if data.make_default:
            self._clear_category_defaults(
                db,
                category=source.category,
            )

        workflow = WorkflowDefinition(
            key=source.key,
            name=(
                data.name
                or source.name
            ),
            description=(
                data.description
                if data.description is not None
                else source.description
            ),
            version=next_version,
            category=source.category,
            workflow_json=self._serialize(
                data.workflow
            ),
            parameter_schema_json=self._serialize(
                data.parameter_schema
            ),
            execution_modes_json=self._serialize(
                [
                    item.value
                    for item in data.execution_modes
                ]
            ),
            metadata_json=self._serialize(
                data.metadata
            ),
            is_active=(
                data.activate_new_version
            ),
            is_default=data.make_default,
            created_by_user_id=(
                created_by_user_id
            ),
        )

        db.add(workflow)
        db.commit()
        db.refresh(workflow)

        cache_invalidation_service.invalidate_workflows(
            workflow_id=workflow.id,
            workflow_key=workflow.key,
            category=workflow.category,
        )

        return self._response(workflow)

    def set_default(
        self,
        db: Session,
        *,
        workflow_id: int,
    ) -> WorkflowDefinitionResponse:
        workflow = self.get(
            db,
            workflow_id=workflow_id,
        )

        if not workflow.is_active:
            raise ConflictException(
                "An inactive workflow cannot "
                "be the default workflow."
            )

        self._clear_category_defaults(
            db,
            category=workflow.category,
            except_id=workflow.id,
        )

        workflow.is_default = True

        db.add(workflow)
        db.commit()
        db.refresh(workflow)

        cache_invalidation_service.invalidate_workflows(
            workflow_id=workflow.id,
            workflow_key=workflow.key,
            category=workflow.category,
        )

        return self._response(workflow)

    def resolve_workflow(
        self,
        db: Session,
        *,
        workflow_id: int | None = None,
        workflow_key: str | None = None,
        category: str = "tryon",
    ) -> WorkflowDefinitionResponse:
        if workflow_id is not None:
            return self.get_response(
                db,
                workflow_id=workflow_id,
            )

        if workflow_key:
            cached = (
                reference_data_cache_service
                .remember_workflow_by_key(
                    workflow_key=workflow_key,
                    loader=lambda: (
                        self._response(workflow)
                        .model_dump(mode="json")
                        if (
                            workflow := (
                                workflow_definition_repository
                                .get_latest_by_key(
                                    db,
                                    key=workflow_key,
                                    active_only=True,
                                )
                            )
                        )
                        else None
                    ),
                )
            )

        else:
            cached = (
                reference_data_cache_service
                .remember_default_workflow(
                    category=category,
                    loader=lambda: (
                        self._response(workflow)
                        .model_dump(mode="json")
                        if (
                            workflow := (
                                workflow_definition_repository
                                .get_default(
                                    db,
                                    category=category,
                                )
                            )
                        )
                        else None
                    ),
                )
            )

        if cached is None:
            raise NotFoundException(
                "No matching active workflow exists."
            )

        result = WorkflowDefinitionResponse(
            **cached
        )

        if not result.is_active:
            raise ConflictException(
                "The selected workflow is inactive."
            )

        return result


workflow_definition_service = (
    WorkflowDefinitionService()
)