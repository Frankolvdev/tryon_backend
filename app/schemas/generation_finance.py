from datetime import datetime
from pydantic import BaseModel
class GenerationFinanceItem(BaseModel):
    execution_id:str; generation_module_id:int|None=None; module_key:str; user_id:int|None=None; status:str
    tokens_consumed:int; recognized_revenue_usd:float; infrastructure_cost_usd:float; gross_profit_usd:float
    gross_margin_percent:float|None=None; traceability_status:str; breakdown:dict; created_at:datetime
class GenerationFinanceSummary(BaseModel):
    total_generations:int; recognized_revenue_usd:float; infrastructure_cost_usd:float; gross_profit_usd:float
    exact_records:int; partial_records:int; unavailable_records:int
class GenerationFinanceListResponse(BaseModel):
    items:list[GenerationFinanceItem]; total:int; skip:int; limit:int; summary:GenerationFinanceSummary
