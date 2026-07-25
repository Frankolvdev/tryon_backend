from app.common.time import utc_now
from app.db.database import SessionLocal
from app.models.audit_entry import AuditEntry
from app.schemas.audit_entry import (
    AuditEntryCreate,
)
from app.schemas.audit_maintenance import (
    AuditSelfTestResponse,
)
from app.services.audit_diff_service import (
    audit_diff_service,
)
from app.services.audit_entry_service import (
    audit_entry_service,
)
from app.services.audit_snapshot_service import (
    audit_snapshot_service,
)


class AuditSelfTestService:
    def run(
        self,
    ) -> AuditSelfTestResponse:
        snapshot_test = False
        redaction_test = False
        diff_test = False
        database_create_test = False
        database_read_test = False
        database_delete_test = False

        temporary_audit_entry_id: int | None = (
            None
        )

        details: dict = {}

        source = {
            "name": "Previous configuration",
            "enabled": False,
            "api_key": "secret-value",
        }

        target = {
            "name": "New configuration",
            "enabled": True,
            "api_key": "another-secret",
        }

        snapshot_before = (
            audit_snapshot_service.snapshot(
                source
            )
        )

        snapshot_after = (
            audit_snapshot_service.snapshot(
                target
            )
        )

        snapshot_test = bool(
            snapshot_before
            and snapshot_after
        )

        redaction_test = bool(
            snapshot_before
            and snapshot_after
            and snapshot_before.get(
                "api_key"
            )
            == "[REDACTED]"
            and snapshot_after.get(
                "api_key"
            )
            == "[REDACTED]"
        )

        diff = audit_diff_service.compare(
            before_data=snapshot_before,
            after_data=snapshot_after,
        )

        diff_test = bool(
            diff.total_changes == 2
            and "name"
            in diff.changed_fields
            and "enabled"
            in diff.changed_fields
            and "api_key"
            not in diff.changed_fields
        )

        details["diff"] = diff.model_dump(
            mode="json"
        )

        db = SessionLocal()

        try:
            created = audit_entry_service.create(
                db,
                data=AuditEntryCreate(
                    actor_type="system",
                    action="audit_self_test",
                    entity_type="audit_test",
                    entity_id="temporary",
                    success=True,
                    before_data=snapshot_before,
                    after_data=snapshot_after,
                    metadata={
                        "temporary": True,
                    },
                    is_restorable=False,
                ),
            )

            temporary_audit_entry_id = created.id
            database_create_test = True

            loaded = db.get(
                AuditEntry,
                created.id,
            )

            database_read_test = (
                loaded is not None
                and loaded.action
                == "audit_self_test"
            )

            if loaded is not None:
                db.delete(loaded)
                db.commit()

                database_delete_test = (
                    db.get(
                        AuditEntry,
                        created.id,
                    )
                    is None
                )

        except Exception as error:
            db.rollback()

            details[
                "database_error"
            ] = str(error)

        finally:
            db.close()

        success = all(
            [
                snapshot_test,
                redaction_test,
                diff_test,
                database_create_test,
                database_read_test,
                database_delete_test,
            ]
        )

        return AuditSelfTestResponse(
            success=success,
            snapshot_test=snapshot_test,
            redaction_test=redaction_test,
            diff_test=diff_test,
            database_create_test=(
                database_create_test
            ),
            database_read_test=(
                database_read_test
            ),
            database_delete_test=(
                database_delete_test
            ),
            temporary_audit_entry_id=(
                temporary_audit_entry_id
            ),
            details=details,
            checked_at=utc_now(),
        )


audit_self_test_service = (
    AuditSelfTestService()
)