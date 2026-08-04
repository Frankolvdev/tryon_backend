from __future__ import annotations
import json
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.token_value_lot import TokenValueLot
from app.models.token_consumption_allocation import TokenConsumptionAllocation

class TokenValueLedgerService:
    def create_lot(self, db: Session, *, user_id:int, tokens:int, source:str, reference_id:str|None, amount_paid_usd:float=0.0, metadata:dict|None=None) -> None:
        if tokens <= 0: return
        amount=max(float(amount_paid_usd or 0),0.0)
        db.add(TokenValueLot(user_id=user_id,source=source,reference_id=reference_id,original_tokens=tokens,remaining_tokens=tokens,amount_paid_usd=Decimal(str(amount)),effective_token_value_usd=Decimal(str(amount/tokens if tokens else 0)),metadata_json=json.dumps(metadata or {},ensure_ascii=False,default=str)))
        db.flush()

    def allocate(self, db:Session, *, user_id:int, execution_id:str, tokens:int, token_transaction_id:int|None) -> None:
        remaining=max(int(tokens),0)
        if remaining<=0:return
        lots=db.execute(select(TokenValueLot).where(TokenValueLot.user_id==user_id,TokenValueLot.remaining_tokens>0).order_by(TokenValueLot.created_at,TokenValueLot.id).with_for_update()).scalars().all()
        for lot in lots:
            if remaining<=0:break
            take=min(remaining,lot.remaining_tokens)
            lot.remaining_tokens-=take
            db.add(TokenConsumptionAllocation(execution_id=execution_id,user_id=user_id,lot_id=lot.id,token_transaction_id=token_transaction_id,tokens_allocated=take,tokens_reversed=0,effective_token_value_usd=lot.effective_token_value_usd))
            db.add(lot); remaining-=take
        if remaining>0:
            # Legacy balance without lot provenance: preserve operation but mark zero-value allocation.
            legacy=TokenValueLot(user_id=user_id,source='legacy_untraced_balance',reference_id=None,original_tokens=remaining,remaining_tokens=0,amount_paid_usd=0,effective_token_value_usd=0,metadata_json='{"traceability":"legacy"}')
            db.add(legacy); db.flush()
            db.add(TokenConsumptionAllocation(execution_id=execution_id,user_id=user_id,lot_id=legacy.id,token_transaction_id=token_transaction_id,tokens_allocated=remaining,tokens_reversed=0,effective_token_value_usd=0))
        db.flush()

    def restore(self, db:Session, *, execution_id:str, tokens:int) -> None:
        remaining=max(int(tokens),0)
        if remaining<=0:return
        allocations=db.execute(select(TokenConsumptionAllocation).where(TokenConsumptionAllocation.execution_id==execution_id,TokenConsumptionAllocation.tokens_allocated>TokenConsumptionAllocation.tokens_reversed).order_by(TokenConsumptionAllocation.id.desc()).with_for_update()).scalars().all()
        for allocation in allocations:
            if remaining<=0:break
            available=allocation.tokens_allocated-allocation.tokens_reversed
            give=min(remaining,available)
            allocation.tokens_reversed+=give
            lot=db.get(TokenValueLot,allocation.lot_id)
            if lot: lot.remaining_tokens+=give; db.add(lot)
            db.add(allocation); remaining-=give
        db.flush()

    def execution_summary(self, db:Session, execution_id:str) -> dict:
        rows=db.execute(select(TokenConsumptionAllocation,TokenValueLot).join(TokenValueLot,TokenValueLot.id==TokenConsumptionAllocation.lot_id).where(TokenConsumptionAllocation.execution_id==execution_id)).all()
        tokens=0; revenue=Decimal('0'); allocations=[]; legacy=False
        for allocation,lot in rows:
            net=max(allocation.tokens_allocated-allocation.tokens_reversed,0)
            value=Decimal(allocation.effective_token_value_usd or 0)
            tokens+=net; revenue+=value*net
            legacy=legacy or lot.source=='legacy_untraced_balance'
            if net: allocations.append({'lot_id':lot.id,'source':lot.source,'reference_id':lot.reference_id,'tokens':net,'effective_token_value_usd':float(value),'recognized_revenue_usd':float(value*net)})
        return {'tokens':tokens,'recognized_revenue_usd':float(revenue),'allocations':allocations,'traceability_status':'partial' if legacy else ('exact' if rows else 'unavailable')}

token_value_ledger_service=TokenValueLedgerService()
