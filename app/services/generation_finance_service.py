from __future__ import annotations
import json
from decimal import Decimal
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.models.generation_financial_record import GenerationFinancialRecord
from app.services.token_value_ledger_service import token_value_ledger_service
from app.services.profitability_surplus_accounting import calculate_profitability_surplus

class GenerationFinanceService:
    def finalize(self,db:Session,*,execution_id:str,module_id:int|None,module_key:str,user_id:int|None,status:str,infrastructure_cost_usd:float|None,billing_breakdown:dict)->GenerationFinancialRecord:
        existing=db.execute(select(GenerationFinancialRecord).where(GenerationFinancialRecord.execution_id==execution_id)).scalar_one_or_none()
        summary=token_value_ledger_service.execution_summary(db,execution_id,expected_tokens=int(billing_breakdown.get('final_tokens') or 0)) if user_id else {'tokens':0,'recognized_revenue_usd':0,'allocations':[],'traceability_status':'unavailable'}
        cash_revenue=float(summary["recognized_revenue_usd"])
        infra=float(infrastructure_cost_usd or 0)
        normal_profit=float(summary.get("profit_without_benefits_usd") or 0)
        benefit=float(summary.get("customer_benefits_usd") or 0)
        profit_after_benefits=float(summary.get("company_profit_usd") or 0)
        profit_applied=bool(billing_breakdown.get("profit_applied", True))
        if not profit_applied:
            normal_profit=0.0
            benefit=0.0
            profit_after_benefits=0.0
            for bag in summary.get("allocations") or []:
                bag["benefit_percent"]=0.0
                bag["normal_profit_per_token_usd"]=0.0
                bag["profit_per_token_after_benefit_usd"]=0.0
                bag["profit_without_benefit_usd"]=0.0
                bag["benefit_given_usd"]=0.0
                bag["company_profit_usd"]=0.0
        rounding_surplus=max(float(billing_breakdown.get("profit_rounding_surplus_usd") or 0),0.0)
        annotated_allocations, profitability_surplus = calculate_profitability_surplus(
            allocations=summary.get("allocations") or [],
            desired_profit_per_token_usd=billing_breakdown.get("desired_profit_per_token_usd"),
            infrastructure_cost_usd=infra,
            rounding_surplus_usd=rounding_surplus,
            profit_applied=profit_applied,
        )
        summary["allocations"] = annotated_allocations
        profitability_surplus_float=float(profitability_surplus)
        company_profit=profit_after_benefits+profitability_surplus_float+rounding_surplus
        economic_total=infra+company_profit
        margin=(company_profit/economic_total*100) if economic_total>0 else None
        payload={
            **billing_breakdown,
            "token_bags_used":summary["allocations"],
            "cash_value_of_used_tokens_usd":round(cash_revenue,6),
            "money_reserved_for_ai_provider_usd":round(infra,6),
            "profit_without_benefits_usd":round(normal_profit,6),
            "benefit_given_to_customer_usd":round(benefit,6),
            "profit_after_customer_benefits_usd":round(profit_after_benefits,6),
            "profitability_surplus_for_company_usd":round(profitability_surplus_float,6),
            "rounding_surplus_for_company_usd":round(rounding_surplus,6),
            "company_profit_usd":round(company_profit,6),
            "economic_total_for_generation_usd":round(economic_total,6),
            "applied_profit_usd":round(profit_after_benefits,9),
            "gross_margin_percent":round(margin,4) if margin is not None else None,
        }
        revenue=economic_total
        profit=company_profit
        record=existing or GenerationFinancialRecord(execution_id=execution_id,module_key=module_key,status=status)
        record.generation_module_id=module_id; record.user_id=user_id; record.status=status; record.tokens_consumed=summary['tokens']; record.recognized_revenue_usd=Decimal(str(round(revenue,6))); record.infrastructure_cost_usd=Decimal(str(round(infra,6))); record.gross_profit_usd=Decimal(str(round(profit,6))); record.gross_margin_percent=Decimal(str(round(margin,4))) if margin is not None else None; record.traceability_status=summary['traceability_status']; record.breakdown_json=json.dumps(payload,ensure_ascii=False,default=str)
        db.add(record); db.flush(); return record

    def _refresh_existing_record(self, db: Session, record: GenerationFinancialRecord) -> None:
        """Rebuild commercial totals from the current token allocations.

        Older records may contain one row per reservation/debit and may not include
        rounding in the company's profit. Recomputing from the ledger keeps the
        API backward-compatible without inventing values.
        """
        try:
            breakdown = json.loads(record.breakdown_json or "{}")
        except (TypeError, ValueError):
            breakdown = {}

        expected_tokens = int(breakdown.get("final_tokens") or record.tokens_consumed or 0)
        summary = token_value_ledger_service.execution_summary(
            db, record.execution_id, expected_tokens=expected_tokens
        )
        if summary.get("traceability_status") == "unavailable":
            return

        infra = float(record.infrastructure_cost_usd or 0)
        profit_after_benefits = float(summary.get("company_profit_usd") or 0)
        profit_applied = bool(breakdown.get("profit_applied", True))
        normal_profit = float(summary.get("profit_without_benefits_usd") or 0)
        benefit = float(summary.get("customer_benefits_usd") or 0)
        if not profit_applied:
            normal_profit = 0.0
            benefit = 0.0
            profit_after_benefits = 0.0
            for bag in summary.get("allocations") or []:
                bag["benefit_percent"] = 0.0
                bag["normal_profit_per_token_usd"] = 0.0
                bag["profit_per_token_after_benefit_usd"] = 0.0
                bag["profit_without_benefit_usd"] = 0.0
                bag["benefit_given_usd"] = 0.0
                bag["company_profit_usd"] = 0.0
        rounding_surplus = max(
            float(
                breakdown.get("rounding_surplus_for_company_usd")
                or breakdown.get("profit_rounding_surplus_usd")
                or 0
            ),
            0.0,
        )
        annotated_allocations, profitability_surplus = calculate_profitability_surplus(
            allocations=summary.get("allocations") or [],
            desired_profit_per_token_usd=breakdown.get("desired_profit_per_token_usd"),
            infrastructure_cost_usd=infra,
            rounding_surplus_usd=rounding_surplus,
            profit_applied=profit_applied,
        )
        summary["allocations"] = annotated_allocations
        profitability_surplus_float = float(profitability_surplus)
        company_profit = profit_after_benefits + profitability_surplus_float + rounding_surplus
        economic_total = infra + company_profit
        margin = company_profit / economic_total * 100 if economic_total > 0 else None

        breakdown.update(
            {
                "token_bags_used": summary.get("allocations") or [],
                "cash_value_of_used_tokens_usd": round(
                    float(summary.get("recognized_revenue_usd") or 0), 6
                ),
                "profit_without_benefits_usd": round(
                    normal_profit, 6
                ),
                "benefit_given_to_customer_usd": round(
                    benefit, 6
                ),
                "profit_after_customer_benefits_usd": round(
                    profit_after_benefits, 6
                ),
                "profitability_surplus_for_company_usd": round(profitability_surplus_float, 6),
                "rounding_surplus_for_company_usd": round(rounding_surplus, 6),
                "company_profit_usd": round(company_profit, 6),
                "economic_total_for_generation_usd": round(economic_total, 6),
                "applied_profit_usd": round(profit_after_benefits, 9),
                "gross_margin_percent": round(margin, 4)
                if margin is not None
                else None,
            }
        )

        record.tokens_consumed = int(summary.get("tokens") or record.tokens_consumed or 0)
        record.recognized_revenue_usd = Decimal(str(round(economic_total, 6)))
        record.gross_profit_usd = Decimal(str(round(company_profit, 6)))
        record.gross_margin_percent = (
            Decimal(str(round(margin, 4))) if margin is not None else None
        )
        record.traceability_status = str(summary.get("traceability_status") or record.traceability_status)
        record.breakdown_json = json.dumps(
            breakdown, ensure_ascii=False, default=str
        )
        db.add(record)

    def list(self,db:Session,*,module_id:int|None=None,status:str|None=None,traceability:str|None=None,skip:int=0,limit:int=100):
        q=select(GenerationFinancialRecord)
        if module_id:q=q.where(GenerationFinancialRecord.generation_module_id==module_id)
        if status:q=q.where(GenerationFinancialRecord.status==status)
        if traceability:q=q.where(GenerationFinancialRecord.traceability_status==traceability)
        total=db.scalar(select(func.count()).select_from(q.subquery())) or 0
        items=db.execute(q.order_by(GenerationFinancialRecord.created_at.desc()).offset(skip).limit(limit)).scalars().all()
        changed=False
        for record in items:
            before=(record.tokens_consumed,record.gross_profit_usd,record.breakdown_json)
            self._refresh_existing_record(db,record)
            after=(record.tokens_consumed,record.gross_profit_usd,record.breakdown_json)
            changed=changed or before!=after
        if changed:
            db.commit()
        return items,total

generation_finance_service=GenerationFinanceService()
