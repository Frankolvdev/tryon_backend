from decimal import Decimal

from app.services.profitability_surplus_accounting import calculate_profitability_surplus


def test_discovers_profitability_surplus_without_counting_rounding_twice():
    rows, total = calculate_profitability_surplus(
        allocations=[{
            "token_bag_id": 1,
            "source": "token_package",
            "tokens_used": 10,
            "normal_profit_per_token_usd": 0.100,
            "profit_per_token_after_benefit_usd": 0.080,
            "infrastructure_capacity_from_tokens_usd": 0.100,
        }],
        desired_profit_per_token_usd=0.103,
        infrastructure_cost_usd=0.067,
        rounding_surplus_usd=0.003,
        profit_applied=True,
    )
    assert total == Decimal("0.030")
    assert Decimal(str(rows[0]["profitability_surplus_usd"])) == Decimal("0.030")
    # Discounted effective profit is deliberately ignored for the comparison.
    assert Decimal(str(rows[0]["profitability_surplus_per_token_usd"])) == Decimal("0.003")


def test_surplus_is_capped_by_real_historical_infrastructure_release():
    rows, total = calculate_profitability_surplus(
        allocations=[{
            "token_bag_id": 1,
            "source": "token_package",
            "tokens_used": 10,
            "normal_profit_per_token_usd": 0.100,
            "infrastructure_capacity_from_tokens_usd": 0.025,
        }],
        desired_profit_per_token_usd=0.110,
        infrastructure_cost_usd=0.020,
        rounding_surplus_usd=0.002,
        profit_applied=True,
    )
    # Candidate is USD 0.10, but only USD 0.003 was actually freed after IA + rounding.
    assert total == Decimal("0.003")
    assert Decimal(str(rows[0]["profitability_surplus_cap_usd"])) == Decimal("0.003")


def test_promotional_and_no_profit_executions_never_create_surplus():
    promotional = [{
        "token_bag_id": 2,
        "source": "promotional_credit",
        "tokens_used": 10,
        "normal_profit_per_token_usd": 0,
        "infrastructure_capacity_from_tokens_usd": 1,
    }]
    _, total_promo = calculate_profitability_surplus(
        allocations=promotional,
        desired_profit_per_token_usd=0.10,
        infrastructure_cost_usd=0.5,
        rounding_surplus_usd=0,
        profit_applied=True,
    )
    _, total_no_profit = calculate_profitability_surplus(
        allocations=[{**promotional[0], "source": "token_package"}],
        desired_profit_per_token_usd=0.10,
        infrastructure_cost_usd=0.5,
        rounding_surplus_usd=0,
        profit_applied=False,
    )
    assert total_promo == 0
    assert total_no_profit == 0
