from __future__ import annotations
import json
from decimal import Decimal
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.models.generation_financial_record import GenerationFinancialRecord
from app.services.token_value_ledger_service import token_value_ledger_service

class GenerationFinanceService:
    def finalize(self,db:Session,*,execution_id:str,module_id:int|None,module_key:str,user_id:int|None,status:str,infrastructure_cost_usd:float|None,billing_breakdown:dict)->GenerationFinancialRecord:
        existing=db.execute(select(GenerationFinancialRecord).where(GenerationFinancialRecord.execution_id==execution_id)).scalar_one_or_none()
        summary=token_value_ledger_service.execution_summary(db,execution_id) if user_id else {'tokens':0,'recognized_revenue_usd':0,'allocations':[],'traceability_status':'unavailable'}
        cash_revenue=float(summary["recognized_revenue_usd"])
        infra=float(infrastructure_cost_usd or 0)
        normal_profit=float(summary.get("profit_without_benefits_usd") or 0)
        benefit=float(summary.get("customer_benefits_usd") or 0)
        company_profit=float(summary.get("company_profit_usd") or 0)
        economic_total=infra+company_profit
        margin=(company_profit/economic_total*100) if economic_total>0 else None
        payload={
            **billing_breakdown,
            "token_bags_used":summary["allocations"],
            "cash_value_of_used_tokens_usd":round(cash_revenue,6),
            "money_reserved_for_ai_provider_usd":round(infra,6),
            "profit_without_benefits_usd":round(normal_profit,6),
            "benefit_given_to_customer_usd":round(benefit,6),
            "company_profit_usd":round(company_profit,6),
            "economic_total_for_generation_usd":round(economic_total,6),
            "gross_margin_percent":round(margin,4) if margin is not None else None,
        }
        revenue=economic_total
        profit=company_profit
        record=existing or GenerationFinancialRecord(execution_id=execution_id,module_key=module_key,status=status)
        record.generation_module_id=module_id; record.user_id=user_id; record.status=status; record.tokens_consumed=summary['tokens']; record.recognized_revenue_usd=Decimal(str(round(revenue,6))); record.infrastructure_cost_usd=Decimal(str(round(infra,6))); record.gross_profit_usd=Decimal(str(round(profit,6))); record.gross_margin_percent=Decimal(str(round(margin,4))) if margin is not None else None; record.traceability_status=summary['traceability_status']; record.breakdown_json=json.dumps(payload,ensure_ascii=False,default=str)
        db.add(record); db.flush(); return record

    def list(self,db:Session,*,module_id:int|None=None,status:str|None=None,traceability:str|None=None,skip:int=0,limit:int=100):
        q=select(GenerationFinancialRecord)
        if module_id:q=q.where(GenerationFinancialRecord.generation_module_id==module_id)
        if status:q=q.where(GenerationFinancialRecord.status==status)
        if traceability:q=q.where(GenerationFinancialRecord.traceability_status==traceability)
        total=db.scalar(select(func.count()).select_from(q.subquery())) or 0
        items=db.execute(q.order_by(GenerationFinancialRecord.created_at.desc()).offset(skip).limit(limit)).scalars().all()
        return items,total

generation_finance_service=GenerationFinanceService()
