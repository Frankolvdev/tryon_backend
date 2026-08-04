# MegaZIP 1 — Backend Profit per Consumed Token

## Architecture
- Infrastructure calculation remains unchanged.
- Each pricing rule now configures `desired_profit_per_token_usd`.
- Final tokens use the closed formula `ceil(infrastructure_cost / (token_value - profit_per_token))`.
- Profit is applied only when the execution billing policy allows it.
- Plans, packages, and percentage coupons discount only `tokens * safe_profit_per_token`.
- Existing `desired_profit_usd` remains as a legacy/audit field; it is no longer the configured profit input.

## Important migration behavior
The new field is nullable and is not guessed from the old per-generation value. Configure every active rule after migration. The backend blocks generations and commercial repricing when profit per token is missing or greater than/equal to token value.

## Commands
```powershell
alembic upgrade head
$env:PYTHONPATH = (Get-Location).Path
python -m compileall -q app tests
python -m pytest tests/test_profit_per_token_architecture_contract.py -v
```
