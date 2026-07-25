import csv
import io
import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.common.time import utc_now
from app.schemas.audit_entry import (
    AuditEntryResponse,
)
from app.schemas.audit_export import (
    AuditExportMetadata,
    AuditExportRequest,
)
from app.services.audit_entry_service import (
    audit_entry_service,
)


class AuditExportService:
    CSV_FIELDS = [
        "id",
        "created_at",
        "actor_user_id",
        "actor_email",
        "actor_type",
        "action",
        "entity_type",
        "entity_id",
        "success",
        "correlation_id",
        "request_id",
        "ip_address",
        "user_agent",
        "error_type",
        "error_message",
        "is_restorable",
        "restored_from_entry_id",
        "before_data",
        "after_data",
        "diff_data",
        "metadata",
    ]

    def _load_entries(
        self,
        db: Session,
        *,
        filters: AuditExportRequest,
    ) -> list[AuditEntryResponse]:
        result = audit_entry_service.list_entries(
            db,
            actor_user_id=filters.actor_user_id,
            actor_email=filters.actor_email,
            actor_type=filters.actor_type,
            action=filters.action,
            entity_type=filters.entity_type,
            entity_id=filters.entity_id,
            success=filters.success,
            correlation_id=filters.correlation_id,
            request_id=filters.request_id,
            is_restorable=filters.is_restorable,
            search=filters.search,
            created_from=filters.created_from,
            created_to=filters.created_to,
            skip=0,
            limit=filters.max_records,
        )

        return result.items

    def _filename(
        self,
        *,
        extension: str,
    ) -> str:
        timestamp = utc_now().strftime(
            "%Y%m%d-%H%M%S"
        )

        return (
            f"audit-entries-"
            f"{timestamp}."
            f"{extension}"
        )

    def _json_safe(
        self,
        value: Any,
    ) -> Any:
        if isinstance(value, datetime):
            return value.isoformat()

        if isinstance(value, dict):
            return {
                str(key): self._json_safe(item)
                for key, item in value.items()
            }

        if isinstance(
            value,
            (
                list,
                tuple,
                set,
            ),
        ):
            return [
                self._json_safe(item)
                for item in value
            ]

        return value

    def _entry_dict(
        self,
        entry: AuditEntryResponse,
    ) -> dict[str, Any]:
        return self._json_safe(
            entry.model_dump()
        )

    def export_json(
        self,
        db: Session,
        *,
        filters: AuditExportRequest,
    ) -> tuple[
        bytes,
        AuditExportMetadata,
    ]:
        entries = self._load_entries(
            db,
            filters=filters,
        )

        filename = self._filename(
            extension="json"
        )

        payload = {
            "generated_at": (
                utc_now().isoformat()
            ),
            "filters": self._json_safe(
                filters.model_dump()
            ),
            "total": len(entries),
            "items": [
                self._entry_dict(entry)
                for entry in entries
            ],
        }

        content = json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            default=str,
        ).encode("utf-8")

        metadata = AuditExportMetadata(
            format="json",
            filename=filename,
            exported_records=len(entries),
            generated_at=utc_now(),
        )

        return content, metadata

    def _csv_value(
        self,
        value: Any,
    ) -> Any:
        if value is None:
            return ""

        if isinstance(value, datetime):
            return value.isoformat()

        if isinstance(
            value,
            (
                dict,
                list,
                tuple,
                set,
            ),
        ):
            return json.dumps(
                self._json_safe(value),
                ensure_ascii=False,
                separators=(",", ":"),
                default=str,
            )

        if isinstance(value, bool):
            return (
                "true"
                if value
                else "false"
            )

        return value

    def export_csv(
        self,
        db: Session,
        *,
        filters: AuditExportRequest,
    ) -> tuple[
        bytes,
        AuditExportMetadata,
    ]:
        entries = self._load_entries(
            db,
            filters=filters,
        )

        filename = self._filename(
            extension="csv"
        )

        output = io.StringIO(
            newline=""
        )

        writer = csv.DictWriter(
            output,
            fieldnames=self.CSV_FIELDS,
            extrasaction="ignore",
        )

        writer.writeheader()

        for entry in entries:
            raw_data = entry.model_dump()

            row = {
                field: self._csv_value(
                    raw_data.get(field)
                )
                for field in self.CSV_FIELDS
            }

            writer.writerow(row)

        content = (
            "\ufeff"
            + output.getvalue()
        ).encode("utf-8")

        metadata = AuditExportMetadata(
            format="csv",
            filename=filename,
            exported_records=len(entries),
            generated_at=utc_now(),
        )

        return content, metadata


audit_export_service = AuditExportService()