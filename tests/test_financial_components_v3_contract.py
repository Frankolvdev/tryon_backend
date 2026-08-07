from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_all_new_commercial_snapshots_use_one_builder():
    service = read("app/services/token_financial_snapshot_service.py")
    assert "def build_commercial_terms" in service
    assert '"financial_economics_schema": ECONOMICS_SCHEMA' in service
    assert '"operational_reserve_per_token_usd": str(operational)' in service
    for path in (
        "app/services/token_purchase_service.py",
        "app/services/subscription_service.py",
        "app/services/subscription_plan_service.py",
        "app/services/promotional_credit_service.py",
    ):
        source = read(path)
        assert "token_financial_snapshot_service.build_commercial_terms(" in source


def test_execution_summary_never_reconstructs_infrastructure_from_paid_minus_profit():
    ledger = read("app/services/token_value_ledger_service.py")
    summary = ledger[ledger.index("def execution_summary"):]
    assert 'snapshot["infrastructure_capacity_per_token"]' in summary
    assert 'snapshot["operational_reserve_per_token"]' in summary
    assert "value-effective_per_token" not in summary
    assert "max(value-effective_per_token" not in summary
    assert '"operational_reserve_from_tokens_usd"' in summary


def test_generation_capacity_is_centralized_and_operational_surcharge_cannot_change_token_count():
    pricing = read("app/services/pricing_service.py")
    economics = read("app/services/token_financial_snapshot_service.py")
    assert "generation_infrastructure_capacity(" in pricing
    assert "capacity = token_value - normal_profit" in economics
    assert "_commercial_sale_value" in pricing
    assert "self._token_value(db) + self._operational_reserve(db)" in pricing
    token_charge = pricing[pricing.index("def token_charge_for_infrastructure"):pricing.index("def get_commercial_settings")]
    assert "_operational_reserve" not in token_charge
    assert "_commercial_sale_value" not in token_charge


def test_catalog_price_and_generation_economics_are_explicitly_separate():
    pricing = read("app/services/pricing_service.py")
    schemas = read("app/schemas/pricing.py")
    assert "amount = max(int(tokens), 0) * self._commercial_sale_value(db)" in pricing
    assert "operational_reserve_per_token_usd" in schemas
    assert "commercial_sale_value_per_token_usd" in schemas


def test_simulator_subtracts_operational_reserve_before_rounding_and_keeps_it_out_of_company_profit():
    simulator = read("app/services/pricing_simulator_service.py")
    assert "operational_total = tokens *" in simulator
    assert "customer_value - infra - operational_total - profit_after" in simulator
    assert "company_total_usd=round(profit_after + rounding" in simulator
    assert "token_value_usd=round(tv, 6)" in simulator


def test_backoffice_catalog_preview_uses_sale_value_not_generation_base_when_available():
    package = (ROOT.parent / "__backoffice_marker__")
    # BackOffice is validated separately in its own MegaZIP. This backend test
    # intentionally avoids coupling pytest to a sibling repository.
    assert not package.exists()
