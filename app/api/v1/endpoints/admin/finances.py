import json
from fastapi import APIRouter,Depends,Query
from sqlalchemy import func,select
from sqlalchemy.orm import Session
from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.models.generation_financial_record import GenerationFinancialRecord
from app.models.user import User
from app.schemas.generation_finance import GenerationFinanceItem,GenerationFinanceListResponse,GenerationFinanceSummary
from app.services.generation_finance_service import generation_finance_service
router=APIRouter()
@router.get('/finances/generations',response_model=GenerationFinanceListResponse)
def list_generation_finances(module_id:int|None=Query(None),status:str|None=Query(None),traceability:str|None=Query(None),skip:int=Query(0,ge=0),limit:int=Query(100,ge=1,le=500),db:Session=Depends(get_db),current_admin:User=Depends(admin_guard)):
    items,total=generation_finance_service.list(db,module_id=module_id,status=status,traceability=traceability,skip=skip,limit=limit)
    q=select(GenerationFinancialRecord)
    if module_id:q=q.where(GenerationFinancialRecord.generation_module_id==module_id)
    if status:q=q.where(GenerationFinancialRecord.status==status)
    if traceability:q=q.where(GenerationFinancialRecord.traceability_status==traceability)
    sub=q.subquery()
    sums=db.execute(select(func.count(),func.coalesce(func.sum(sub.c.recognized_revenue_usd),0),func.coalesce(func.sum(sub.c.infrastructure_cost_usd),0),func.coalesce(func.sum(sub.c.gross_profit_usd),0))).one()
    counts=dict(db.execute(select(sub.c.traceability_status,func.count()).group_by(sub.c.traceability_status)).all())
    def item(r):
      try:b=json.loads(r.breakdown_json or '{}')
      except:b={}
      return GenerationFinanceItem(execution_id=r.execution_id,generation_module_id=r.generation_module_id,module_key=r.module_key,user_id=r.user_id,status=r.status,tokens_consumed=r.tokens_consumed,recognized_revenue_usd=float(r.recognized_revenue_usd),infrastructure_cost_usd=float(r.infrastructure_cost_usd),gross_profit_usd=float(r.gross_profit_usd),gross_margin_percent=float(r.gross_margin_percent) if r.gross_margin_percent is not None else None,traceability_status=r.traceability_status,breakdown=b,created_at=r.created_at)
    return GenerationFinanceListResponse(items=[item(r) for r in items],total=total,skip=skip,limit=limit,summary=GenerationFinanceSummary(total_generations=int(sums[0]),recognized_revenue_usd=float(sums[1]),infrastructure_cost_usd=float(sums[2]),gross_profit_usd=float(sums[3]),exact_records=int(counts.get('exact',0)),partial_records=int(counts.get('partial',0)),unavailable_records=int(counts.get('unavailable',0))))
