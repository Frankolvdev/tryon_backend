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
        rows=db.execute(
            select(TokenConsumptionAllocation,TokenValueLot)
            .join(TokenValueLot,TokenValueLot.id==TokenConsumptionAllocation.lot_id)
            .where(TokenConsumptionAllocation.execution_id==execution_id)
            .order_by(TokenConsumptionAllocation.id)
        ).all()
        tokens=0
        cash_revenue=Decimal("0")
        normal_profit=Decimal("0")
        discount_given=Decimal("0")
        net_profit=Decimal("0")
        grouped:dict[int,dict]={}
        legacy=False
        for allocation,lot in rows:
            net=max(allocation.tokens_allocated-allocation.tokens_reversed,0)
            if not net:
                continue
            value=Decimal(allocation.effective_token_value_usd or 0)
            try:
                metadata=json.loads(lot.metadata_json or "{}")
            except (TypeError,ValueError):
                metadata={}
            normal_per_token=Decimal(str(metadata.get("normal_profit_per_token_usd") or 0))
            discount_percent=Decimal(str(metadata.get("profit_discount_percent") or 0))
            effective_per_token=Decimal(str(
                metadata.get("effective_profit_per_token_usd")
                if metadata.get("effective_profit_per_token_usd") is not None
                else normal_per_token*(Decimal("1")-discount_percent/Decimal("100"))
            ))
            row_normal=normal_per_token*net
            row_net=effective_per_token*net
            row_discount=max(Decimal("0"),row_normal-row_net)
            tokens+=net
            cash_revenue+=value*net
            normal_profit+=row_normal
            discount_given+=row_discount
            net_profit+=row_net
            legacy=legacy or lot.source=="legacy_untraced_balance"
            current=grouped.get(lot.id)
            if current is None:
                current={
                    "token_bag_id":lot.id,
                    "source":lot.source,
                    "source_label":metadata.get("source_label") or metadata.get("source") or lot.source,
                    "reference_id":lot.reference_id,
                    "tokens_used":0,
                    "benefit_percent":float(discount_percent),
                    "normal_profit_per_token_usd":float(normal_per_token),
                    "profit_per_token_after_benefit_usd":float(effective_per_token),
                    "profit_without_benefit_usd":0.0,
                    "benefit_given_usd":0.0,
                    "company_profit_usd":0.0,
                    "effective_token_value_usd":float(value),
                    "cash_value_at_purchase_usd":0.0,
                    "coupon_code":metadata.get("coupon_code"),
                    "plan_name":metadata.get("plan_name"),
                }
                grouped[lot.id]=current
            current["tokens_used"]+=net
            current["profit_without_benefit_usd"]+=float(row_normal)
            current["benefit_given_usd"]+=float(row_discount)
            current["company_profit_usd"]+=float(row_net)
            current["cash_value_at_purchase_usd"]+=float(value*net)
        allocations=list(grouped.values())
        return {
            "tokens":tokens,
            "recognized_revenue_usd":float(cash_revenue),
            "profit_without_benefits_usd":float(normal_profit),
            "customer_benefits_usd":float(discount_given),
            "company_profit_usd":float(net_profit),
            "allocations":allocations,
            "traceability_status":"partial" if legacy else ("exact" if rows else "unavailable"),
        }

token_value_ledger_service=TokenValueLedgerService()
