from datetime import datetime
from typing import Any

from fastapi import Request
from sqlalchemy import inspect as sqlalchemy_inspect
from sqlalchemy.orm import Session

from app.common.exceptions import (
    ConflictException,
    NotFoundException,
)
from app.models.audit_entry import AuditEntry
from app.models.user import User
from app.schemas.audit_restoration import (
    AuditRestorePreviewResponse,
    AuditRestoreRequest,
    AuditRestoreResponse,
)
from app.services.audit_entry_service import (
    audit_entry_service,
)
from app.services.audit_restore_registry_service import (
    AuditRestoreEntityConfiguration,
    audit_restore_registry_service,
)
from app.services.audit_snapshot_service import (
    audit_snapshot_service,
)
from app.services.cache_invalidation_service import (
    cache_invalidation_service,
)


class AuditRestorationService:
    NEVER_RESTORE_FIELDS = {
        "id",
        "created_at",
        "updated_at",
        "deleted_at",
        "created_by_user_id",
        "updated_by_user_id",
        "password",
        "password_hash",
        "hashed_password",
        "access_token",
        "refresh_token",
        "api_key",
        "secret",
        "secret_key",
        "credentials_json",
        "encrypted_credentials",
        "private_key",
    }

    def _get_audit_entry(
        self,
        db: Session,
        *,
        audit_entry_id: int,
    ) -> AuditEntry:
        entry = audit_entry_service.get(
            db,
            entry_id=audit_entry_id,
        )

        if not entry.is_restorable:
            raise ConflictException(
                "This audit entry is not restorable."
            )

        if not entry.entity_id:
            raise ConflictException(
                "The audit entry does not reference a concrete entity."
            )

        if not entry.before_data:
            raise ConflictException(
                "The audit entry has no previous snapshot to restore."
            )

        return entry

    def _model_column_names(
        self,
        configuration: AuditRestoreEntityConfiguration,
    ) -> set[str]:
        mapper = sqlalchemy_inspect(
            configuration.model
        )

        return {
            column.key
            for column in mapper.columns
        }

    def _filter_restore_data(
        self,
        *,
        configuration: AuditRestoreEntityConfiguration,
        restore_snapshot: dict[str, Any],
        restore_null_values: bool,
    ) -> tuple[
        dict[str, Any],
        list[str],
        list[str],
    ]:
        model_columns = self._model_column_names(
            configuration
        )

        allowed_fields = (
            set(configuration.mutable_fields)
            & model_columns
        )

        protected_fields = (
            set(configuration.protected_fields)
            | self.NEVER_RESTORE_FIELDS
        )

        restore_data: dict[str, Any] = {}
        ignored_fields: list[str] = []
        missing_fields: list[str] = []

        for field, value in restore_snapshot.items():
            if field in protected_fields:
                ignored_fields.append(field)
                continue

            if field not in allowed_fields:
                ignored_fields.append(field)
                continue

            if (
                value is None
                and not restore_null_values
            ):
                ignored_fields.append(field)
                continue

            if value == "[REDACTED]":
                ignored_fields.append(field)
                continue

            restore_data[field] = value

        for field in allowed_fields:
            if field not in restore_snapshot:
                missing_fields.append(field)

        return (
            restore_data,
            sorted(set(ignored_fields)),
            sorted(set(missing_fields)),
        )

    def _changed_fields(
        self,
        *,
        entity: Any,
        restore_data: dict[str, Any],
    ) -> list[str]:
        return sorted(
            field
            for field, value in restore_data.items()
            if getattr(
                entity,
                field,
                None,
            )
            != value
        )

    def _check_concurrency(
        self,
        *,
        entity: Any,
        expected_updated_at: str | None,
    ) -> None:
        if not expected_updated_at:
            return

        current_updated_at = getattr(
            entity,
            "updated_at",
            None,
        )

        if current_updated_at is None:
            return

        try:
            expected = datetime.fromisoformat(
                expected_updated_at.replace(
                    "Z",
                    "+00:00",
                )
            )
        except ValueError as error:
            raise ConflictException(
                "expected_updated_at is invalid."
            ) from error

        current_value = current_updated_at

        if (
            getattr(
                current_value,
                "tzinfo",
                None,
            )
            is None
            and expected.tzinfo is not None
        ):
            expected = expected.replace(
                tzinfo=None
            )

        if current_value != expected:
            raise ConflictException(
                "The entity was modified after the version was loaded. "
                "Refresh the page before restoring it."
            )

    def _invalidate_cache(
        self,
        *,
        configuration: AuditRestoreEntityConfiguration,
        entity: Any,
    ) -> None:
        method = configuration.invalidation_method

        if method == "workflows":
            cache_invalidation_service.invalidate_workflows(
                workflow_id=getattr(
                    entity,
                    "id",
                    None,
                ),
                workflow_key=getattr(
                    entity,
                    "key",
                    None,
                ),
                category=getattr(
                    entity,
                    "category",
                    None,
                ),
            )
            return

        if method == "pricing":
            cache_invalidation_service.invalidate_pricing(
                pricing_key=getattr(
                    entity,
                    "key",
                    None,
                ),
            )
            return

        if method == "settings":
            cache_invalidation_service.invalidate_system_settings(
                setting_key=getattr(
                    entity,
                    "key",
                    None,
                ),
            )
            return

        if method == "feature_flags":
            cache_invalidation_service.invalidate_feature_flags(
                flag_key=getattr(
                    entity,
                    "key",
                    None,
                ),
            )
            return

        if method == "integrations":
            provider = getattr(
                entity,
                "provider",
                None,
            )

            if provider is not None:
                provider = (
                    provider.value
                    if hasattr(
                        provider,
                        "value",
                    )
                    else str(provider)
                )

            cache_invalidation_service.invalidate_integrations(
                provider=provider,
            )
            return

        if method == "subscription_plans":
            cache_invalidation_service.invalidate_subscription_plans(
                plan_id=getattr(
                    entity,
                    "id",
                    None,
                ),
            )
            return

        if method == "token_packages":
            cache_invalidation_service.invalidate_token_packages(
                package_id=getattr(
                    entity,
                    "id",
                    None,
                ),
            )

    def preview(
        self,
        db: Session,
        *,
        audit_entry_id: int,
        restore_null_values: bool = True,
    ) -> AuditRestorePreviewResponse:
        entry = self._get_audit_entry(
            db,
            audit_entry_id=audit_entry_id,
        )

        configuration = (
            audit_restore_registry_service.get(
                entry.entity_type
            )
        )

        if configuration is None:
            return AuditRestorePreviewResponse(
                audit_entry_id=entry.id,
                entity_type=entry.entity_type,
                entity_id=str(
                    entry.entity_id
                ),
                can_restore=False,
                reason=(
                    "This entity type is not registered for restoration."
                ),
                current_data=None,
                restore_data=entry.before_data,
            )

        entity = (
            audit_restore_registry_service.get_entity(
                db,
                entity_type=entry.entity_type,
                entity_id=str(
                    entry.entity_id
                ),
            )
        )

        if entity is None:
            return AuditRestorePreviewResponse(
                audit_entry_id=entry.id,
                entity_type=entry.entity_type,
                entity_id=str(
                    entry.entity_id
                ),
                can_restore=False,
                reason=(
                    "The target entity no longer exists."
                ),
                current_data=None,
                restore_data=entry.before_data,
            )

        (
            restore_data,
            ignored_fields,
            missing_fields,
        ) = self._filter_restore_data(
            configuration=configuration,
            restore_snapshot=entry.before_data,
            restore_null_values=(
                restore_null_values
            ),
        )

        changed_fields = self._changed_fields(
            entity=entity,
            restore_data=restore_data,
        )

        return AuditRestorePreviewResponse(
            audit_entry_id=entry.id,
            entity_type=entry.entity_type,
            entity_id=str(
                entry.entity_id
            ),
            can_restore=bool(
                restore_data
            ),
            reason=(
                None
                if restore_data
                else (
                    "The snapshot has no safe fields that can be restored."
                )
            ),
            current_data=(
                audit_snapshot_service.snapshot(
                    entity
                )
            ),
            restore_data=restore_data,
            changed_fields=changed_fields,
            ignored_fields=ignored_fields,
            missing_fields=missing_fields,
        )

    def restore(
        self,
        db: Session,
        *,
        audit_entry_id: int,
        data: AuditRestoreRequest,
        current_admin: User,
        request: Request,
    ) -> AuditRestoreResponse:
        source_entry = self._get_audit_entry(
            db,
            audit_entry_id=audit_entry_id,
        )

        configuration = (
            audit_restore_registry_service.require(
                source_entry.entity_type
            )
        )

        entity = (
            audit_restore_registry_service.get_entity(
                db,
                entity_type=source_entry.entity_type,
                entity_id=str(
                    source_entry.entity_id
                ),
            )
        )

        if entity is None:
            raise NotFoundException(
                "The entity that should be restored no longer exists."
            )

        self._check_concurrency(
            entity=entity,
            expected_updated_at=(
                data.expected_updated_at
            ),
        )

        before_restore = (
            audit_snapshot_service.snapshot(
                entity
            )
        )

        (
            restore_data,
            ignored_fields,
            _,
        ) = self._filter_restore_data(
            configuration=configuration,
            restore_snapshot=(
                source_entry.before_data or {}
            ),
            restore_null_values=(
                data.restore_null_values
            ),
        )

        changed_fields = self._changed_fields(
            entity=entity,
            restore_data=restore_data,
        )

        if not changed_fields:
            raise ConflictException(
                "The entity already matches the selected audited version."
            )

        restoration_entry = None

        try:
            for field in changed_fields:
                setattr(
                    entity,
                    field,
                    restore_data[field],
                )

            db.add(entity)
            db.flush()

            after_restore = (
                audit_snapshot_service.snapshot(
                    entity
                )
            )

            restoration_entry = (
                audit_entry_service.record(
                    db,
                    action="restore",
                    entity_type=(
                        source_entry.entity_type
                    ),
                    entity_id=(
                        source_entry.entity_id
                    ),
                    actor=current_admin,
                    before=before_restore,
                    after=after_restore,
                    request=request,
                    metadata={
                        "reason": data.reason,
                        "source_audit_entry_id": (
                            source_entry.id
                        ),
                        "ignored_fields": (
                            ignored_fields
                        ),
                        "restored_fields": (
                            changed_fields
                        ),
                    },
                    is_restorable=True,
                    restored_from_entry_id=(
                        source_entry.id
                    ),
                    commit=False,
                )
            )

            db.commit()
            db.refresh(entity)

        except Exception as error:
            db.rollback()

            audit_entry_service.safe_record(
                db,
                action="restore",
                entity_type=(
                    source_entry.entity_type
                ),
                entity_id=(
                    source_entry.entity_id
                ),
                actor=current_admin,
                before=before_restore,
                after=None,
                request=request,
                success=False,
                exception=error,
                metadata={
                    "reason": data.reason,
                    "source_audit_entry_id": (
                        source_entry.id
                    ),
                },
            )

            raise

        self._invalidate_cache(
            configuration=configuration,
            entity=entity,
        )

        return AuditRestoreResponse(
            success=True,
            restored_entity_type=(
                source_entry.entity_type
            ),
            restored_entity_id=str(
                source_entry.entity_id
            ),
            source_audit_entry_id=(
                source_entry.id
            ),
            restoration_audit_entry_id=(
                restoration_entry.id
                if restoration_entry is not None
                else None
            ),
            changed_fields=changed_fields,
            ignored_fields=ignored_fields,
            before_data=before_restore,
            after_data=after_restore,
            message=(
                "The audited version was restored successfully."
            ),
        )


audit_restoration_service = (
    AuditRestorationService()
)