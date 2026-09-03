from pathlib import Path


def test_used_subscription_plans_are_archived_instead_of_hard_deleted():
    source = Path("app/services/subscription_plan_service.py").read_text(
        encoding="utf-8"
    )

    assert "user_subscription_repository.count_filtered" in source
    assert '"is_active": False' in source
    assert '"is_public": False' in source
    assert "if subscription_count > 0:" in source
    assert "subscription_plan_repository.delete" in source


def test_delete_endpoint_reports_archive_without_integrity_error():
    source = Path(
        "app/api/v1/endpoints/admin/subscription_plans.py"
    ).read_text(encoding="utf-8")

    assert "was_archived = subscription_plan_service.delete_plan" in source
    assert "admin_subscription_plan_archived" in source
    assert "subscription history" in source
