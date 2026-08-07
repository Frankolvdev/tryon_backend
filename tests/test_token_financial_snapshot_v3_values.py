from decimal import Decimal

from app.services.token_financial_snapshot_service import token_financial_snapshot_service

D = Decimal


def test_25_percent_profit_discount_never_touches_ai_reserve():
    terms = token_financial_snapshot_service.build_commercial_terms(
        token_value_usd="0.11",
        normal_profit_per_token_usd="0.103",
        profit_discount_percent="25",
    )
    assert D(terms["infrastructure_capacity_per_token_usd"]) == D("0.007")
    assert D(terms["operational_reserve_per_token_usd"]) == D("0")
    assert D(terms["effective_profit_per_token_usd"]) == D("0.07725")


def test_historical_underpriced_purchase_reduces_profit_not_ai_reserve():
    terms = token_financial_snapshot_service.build_commercial_terms(
        token_value_usd="0.11",
        normal_profit_per_token_usd="0.103",
        profit_discount_percent="25",
    )
    normalized = token_financial_snapshot_service.normalize_new_lot_snapshot(
        terms,
        paid_value_per_token=D("51.15") / D("660"),
    )
    assert D(normalized["infrastructure_capacity_per_token_usd"]) == D("0.007")
    assert D(normalized["effective_profit_per_token_usd"]) == D("0.0705")
    assert normalized["profit_adjusted_to_protect_infrastructure"] is True


def test_operational_component_is_independent_from_ai_and_profit():
    terms = token_financial_snapshot_service.build_commercial_terms(
        token_value_usd="0.11",
        normal_profit_per_token_usd="0.103",
        profit_discount_percent="25",
        operational_reserve_per_token_usd="0.002",
    )
    normalized = token_financial_snapshot_service.normalize_new_lot_snapshot(
        terms,
        paid_value_per_token="0.08625",
    )
    assert D(normalized["infrastructure_capacity_per_token_usd"]) == D("0.007")
    assert D(normalized["operational_reserve_per_token_usd"]) == D("0.002")
    assert D(normalized["effective_profit_per_token_usd"]) == D("0.07725")
    assert (
        D(normalized["infrastructure_capacity_per_token_usd"])
        + D(normalized["operational_reserve_per_token_usd"])
        + D(normalized["effective_profit_per_token_usd"])
    ) == D("0.08625")


def test_generation_capacity_does_not_include_operational_surcharge():
    capacity = token_financial_snapshot_service.generation_infrastructure_capacity(
        token_value_usd="0.11",
        normal_profit_per_token_usd="0.103",
    )
    assert capacity == D("0.007")


def test_promotional_snapshot_keeps_zero_profit_and_explicit_ai_capacity():
    snapshot = {
        "promotional_credit_funded": True,
        "infrastructure_capacity_per_token_usd": "0.007",
        "operational_reserve_per_token_usd": "0",
        "normal_profit_per_token_usd": "0",
        "effective_profit_per_token_usd": "0",
    }
    normalized = token_financial_snapshot_service.normalize_new_lot_snapshot(
        snapshot,
        paid_value_per_token="0",
    )
    components = token_financial_snapshot_service.read_lot_snapshot(
        metadata=normalized,
        paid_value_per_token="0",
    )
    assert components.infrastructure_capacity_per_token == D("0.007")
    assert components.operational_reserve_per_token == D("0")
    assert components.effective_profit_per_token == D("0")
