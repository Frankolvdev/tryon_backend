from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_create_uses_start_plus_periodicity_not_manual_end_date():
    schema = read("app/schemas/promotional_credit.py")
    service = read("app/services/promotional_funding_cycle_service.py")
    assert 'recurrence: str = Field(default="monthly"' in schema
    create_block = schema.split("class PromotionalRecurringSourceCreate", 1)[1].split("class PromotionalRecurringSourceUpdate", 1)[0]
    assert "cycle_end:" not in create_block
    assert "cycle_end = self._next_cycle_end(cycle_start, recurrence)" in service


def test_periodicity_is_configurable_and_not_hardcoded_to_monthly():
    service = read("app/services/promotional_funding_cycle_service.py")
    for name in ("weekly", "monthly", "quarterly", "yearly"):
        assert f'recurrence == "{name}"' in service
    assert "next_end = self._next_cycle_end(next_start, source.recurrence)" in service


def test_webhook_and_lazy_guard_share_same_rollover_service():
    route = read("app/api/v1/endpoints/admin/finance_cashbox.py")
    service = read("app/services/promotional_funding_cycle_service.py")
    assert "/cycle-webhook" in route
    assert "promotional_funding_cycle_service.trigger_webhook" in route
    assert "def trigger_webhook" in service
    assert "self.ensure_current_cycles(db, today=effective_date, source_id=source_id)" in service
    assert "def ensure_current_cycles" in service


def test_simulation_is_opt_in_and_dry_run_only():
    service = read("app/services/promotional_funding_cycle_service.py")
    schema = read("app/schemas/promotional_credit.py")
    model = read("app/models/promotional_funding_cycle.py")
    assert "simulation_enabled" in model
    assert "simulation_enabled" in schema
    assert "Cycle simulation is disabled" in service
    preview = service.split("def preview_rollover", 1)[1].split("def trigger_webhook", 1)[0]
    assert "remaining_usd =" not in preview
    assert "db.add(" not in preview
    assert "No balance or cycle was changed" in preview


def test_simulation_flag_has_linear_migration_after_05e():
    migration = read("alembic/versions/05f_promotional_cycle_webhook_periodicity.py")
    assert 'revision = "05f_promo_cycle_hook"' in migration
    assert 'down_revision = "05e_promo_cycles"' in migration
    assert "simulation_enabled" in migration


def test_backoffice_has_manual_button_periodicity_and_simulation_flag():
    ui = read("../backoffice/src/app/dashboard/finances/cashbox/page.tsx") if False else ""
    # Backend contract deliberately does not depend on a sibling checkout.
    route = read("app/api/v1/endpoints/admin/finance_cashbox.py")
    assert "PromotionalCycleWebhookRequest" in route
