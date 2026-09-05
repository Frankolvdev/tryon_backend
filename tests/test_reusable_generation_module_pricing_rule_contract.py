from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_generation_module_owns_reusable_pricing_rule_reference():
    model = read("app/models/generation_module.py")
    assert 'ForeignKey("pricing_rules.id", ondelete="SET NULL")' in model
    assert "pricing_rule_id:" in model


def test_binding_never_clones_or_moves_pricing_rule():
    service = read("app/services/generation_module_service.py")
    binding = service.split("def _bind_pricing_rule", 1)[1].split("def list_modules", 1)[0]
    assert "_copy_pricing_rule_for_module" not in service
    assert "module.pricing_rule_id = selected.id" in binding
    assert "selected.generation_module_id =" not in binding
    assert "PricingRule(" not in binding


def test_clone_reuses_same_pricing_rule_id():
    operations = read("app/services/generation_module_operations_service.py")
    clone = operations.split("def clone", 1)[1].split("def publish", 1)[0]
    assert "pricing_rule_id=source.pricing_rule_id" in clone


def test_applied_pricing_runs_per_module_without_changing_formula_inputs():
    pricing = read("app/services/pricing_service.py")
    applied = pricing.split("def list_applied_rules", 1)[1]
    assert "GenerationModule.pricing_rule_id.is_not(None)" in applied
    assert "rule = db.get(PricingRule, module.pricing_rule_id)" in applied
    assert "desired_profit_per_token_usd" in applied
    assert "technical_margin_seconds" in applied
    assert "token_charge_for_infrastructure" in applied


def test_migration_preserves_rows_and_only_deactivates_proven_legacy_copies():
    migration = read("alembic/versions/06g_reusable_generation_module_pricing_rules.py")
    assert "pricing_rule_id" in migration
    assert "canonical_rule" in migration
    assert "proven_copy_ids" in migration
    assert ".values(is_active=False)" in migration
    assert "delete(" not in migration
    assert ".values(generation_module_id=None)" in migration
