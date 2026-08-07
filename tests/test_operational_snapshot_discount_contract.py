from decimal import Decimal as D
from app.services.token_financial_snapshot_service import token_financial_snapshot_service

def test_discount_reduces_only_profit_and_preserves_ai_and_operation():
    terms=token_financial_snapshot_service.build_commercial_terms(
        token_value_usd="0.110", normal_profit_per_token_usd="0.103",
        operational_reserve_per_token_usd="0.002", profit_discount_percent="25",
    )
    assert D(terms["infrastructure_capacity_per_token_usd"]) == D("0.007")
    assert D(terms["operational_reserve_per_token_usd"]) == D("0.002")
    assert D(terms["effective_profit_per_token_usd"]) == D("0.07725")
    assert D(terms["token_value_usd"]) == D("0.110")

def test_future_operational_changes_cannot_change_existing_snapshot():
    terms=token_financial_snapshot_service.build_commercial_terms(
        token_value_usd="0.110", normal_profit_per_token_usd="0.103",
        operational_reserve_per_token_usd="0.002", profit_discount_percent="0",
    )
    normalized=token_financial_snapshot_service.normalize_new_lot_snapshot(
        terms, paid_value_per_token="0.112"
    )
    components=token_financial_snapshot_service.read_lot_snapshot(
        metadata=normalized, paid_value_per_token="0.112", fallback_profit_per_token_usd="999"
    )
    assert components.operational_reserve_per_token == D("0.002")
    assert components.infrastructure_capacity_per_token == D("0.007")
