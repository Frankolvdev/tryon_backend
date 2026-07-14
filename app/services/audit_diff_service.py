from typing import Any

from app.common.audit_enums import (
    AuditChangeType,
)
from app.schemas.audit_entry import (
    AuditDiffResponse,
    AuditFieldChange,
)


class AuditDiffService:
    def compare(
        self,
        *,
        before_data: dict[str, Any] | None,
        after_data: dict[str, Any] | None,
    ) -> AuditDiffResponse:
        before = before_data or {}
        after = after_data or {}

        all_fields = sorted(
            set(before.keys())
            | set(after.keys())
        )

        changes: list[AuditFieldChange] = []

        added_fields: list[str] = []
        removed_fields: list[str] = []
        changed_fields: list[str] = []

        for field in all_fields:
            exists_before = field in before
            exists_after = field in after

            before_value = before.get(field)
            after_value = after.get(field)

            if not exists_before and exists_after:
                change_type = (
                    AuditChangeType.ADDED.value
                )

                added_fields.append(field)

            elif exists_before and not exists_after:
                change_type = (
                    AuditChangeType.REMOVED.value
                )

                removed_fields.append(field)

            elif before_value != after_value:
                change_type = (
                    AuditChangeType.CHANGED.value
                )

                changed_fields.append(field)

            else:
                continue

            changes.append(
                AuditFieldChange(
                    field=field,
                    change_type=change_type,
                    before=before_value,
                    after=after_value,
                )
            )

        return AuditDiffResponse(
            before_data=before_data,
            after_data=after_data,
            changes=changes,
            added_fields=added_fields,
            removed_fields=removed_fields,
            changed_fields=changed_fields,
            total_changes=len(changes),
        )

    def as_dict(
        self,
        *,
        before_data: dict[str, Any] | None,
        after_data: dict[str, Any] | None,
    ) -> dict[str, Any]:
        return self.compare(
            before_data=before_data,
            after_data=after_data,
        ).model_dump(
            mode="json"
        )


audit_diff_service = AuditDiffService()