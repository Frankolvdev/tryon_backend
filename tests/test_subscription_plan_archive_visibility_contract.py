from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_safe_delete_marks_used_plan_as_archived() -> None:
    source = (ROOT / "app/services/subscription_plan_service.py").read_text()
    assert '"archived_at": utc_now()' in source
    assert '"is_active": False' in source
    assert '"is_public": False' in source


def test_admin_catalog_excludes_archived_plans_by_default() -> None:
    source = (ROOT / "app/repositories/subscription_plan_repository.py").read_text()
    assert "include_archived: bool = False" in source
    assert "SubscriptionPlan.archived_at.is_(None)" in source


def test_migration_recovers_previously_archived_used_plans() -> None:
    source = (
        ROOT
        / "alembic/versions/8a6d1e4f2b90_add_subscription_plan_archived_at.py"
    ).read_text()
    assert "user_subscriptions" in source
    assert "subscription_plan_id = plan.id" in source
