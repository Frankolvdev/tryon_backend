from __future__ import annotations
import json
from decimal import Decimal, ROUND_CEILING
from app.common.time import utc_now
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.common.exceptions import ConflictException
from app.models.token_value_lot import TokenValueLot
from app.models.token_consumption_allocation import TokenConsumptionAllocation

class TokenValueLedgerService:
    @staticmethod
    def _parse_metadata(lot: TokenValueLot) -> dict:
        try:
            value = json.loads(lot.metadata_json or "{}")
            return value if isinstance(value, dict) else {}
        except (TypeError, ValueError):
            return {}

    @staticmethod
    def _decimal(value: object, default: Decimal = Decimal("0")) -> Decimal:
        try:
            return Decimal(str(value))
        except (TypeError, ValueError, ArithmeticError):
            return default

    def _snapshot_for_lot(
        self,
        lot: TokenValueLot,
        *,
        fallback_profit_per_token_usd: float = 0.0,
    ) -> dict:
        metadata = self._parse_metadata(lot)
        paid_value = self._decimal(lot.effective_token_value_usd)
        has_frozen_profit = (
            metadata.get("effective_profit_per_token_usd") is not None
            or metadata.get("normal_profit_per_token_usd") is not None
        )
        normal_profit = self._decimal(metadata.get("normal_profit_per_token_usd"))
        discount = self._decimal(metadata.get("profit_discount_percent"))
        if metadata.get("effective_profit_per_token_usd") is not None:
            effective_profit = self._decimal(metadata.get("effective_profit_per_token_usd"))
        elif has_frozen_profit:
            effective_profit = normal_profit * (Decimal("1") - discount / Decimal("100"))
        else:
            # Compatibility only for genuinely old lots that predate commercial snapshots.
            effective_profit = min(
                max(self._decimal(fallback_profit_per_token_usd), Decimal("0")),
                max(paid_value - Decimal("0.000000001"), Decimal("0")),
            )
        frozen_capacity = metadata.get("infrastructure_capacity_per_token_usd")
        if frozen_capacity is not None:
            capacity = max(self._decimal(frozen_capacity), Decimal("0"))
        else:
            capacity = max(paid_value - effective_profit, Decimal("0"))
        return {
            "paid_value_per_token": paid_value,
            "normal_profit_per_token": normal_profit,
            "effective_profit_per_token": effective_profit,
            "infrastructure_capacity_per_token": capacity,
            "snapshot_source": "frozen_v2" if frozen_capacity is not None else ("frozen_legacy" if has_frozen_profit else "legacy_current_rule_fallback"),
            "metadata": metadata,
        }

    def create_lot(self, db: Session, *, user_id:int, tokens:int, source:str, reference_id:str|None, amount_paid_usd:float=0.0, metadata:dict|None=None) -> None:
        if tokens <= 0: return
        amount=max(float(amount_paid_usd or 0),0.0)
        paid_per_token=Decimal(str(amount/tokens if tokens else 0))
        snapshot=dict(metadata or {})
        normal_profit=self._decimal(snapshot.get("normal_profit_per_token_usd"))
        discount=self._decimal(snapshot.get("profit_discount_percent"))
        effective_profit=self._decimal(
            snapshot.get("effective_profit_per_token_usd"),
            normal_profit*(Decimal("1")-discount/Decimal("100")),
        )
        effective_profit=max(min(effective_profit,paid_per_token),Decimal("0"))
        snapshot.update({
            "financial_snapshot_version": 2,
            "effective_paid_token_value_usd": str(paid_per_token),
            "infrastructure_capacity_per_token_usd": str(max(paid_per_token-effective_profit,Decimal("0"))),
        })
        db.add(TokenValueLot(user_id=user_id,source=source,reference_id=reference_id,original_tokens=tokens,remaining_tokens=tokens,amount_paid_usd=Decimal(str(amount)),effective_token_value_usd=paid_per_token,metadata_json=json.dumps(snapshot,ensure_ascii=False,default=str)))
        db.flush()

    def quote_fifo_infrastructure_charge(
        self, db: Session, *, user_id: int, execution_id: str | None,
        infrastructure_cost_usd: float, apply_profit: bool,
        fallback_profit_per_token_usd: float = 0.0,
    ) -> dict:
        """Quote a token charge using the exact FIFO lots that will fund it.

        Existing allocations for the execution are considered first, followed by
        the user's remaining lots in FIFO order. This mirrors reconcile(): refunds
        reverse the newest allocations while extra debits consume the next FIFO lots.
        """
        cost=max(self._decimal(infrastructure_cost_usd),Decimal("0"))
        if cost<=0:
            return {"tokens":0,"charged_usd":0.0,"configured_profit_usd":0.0,"rounding_surplus_usd":0.0,"infrastructure_capacity_usd":0.0,"bags":[],"traceability_status":"exact"}
        segments=[]
        used_lot_ids=set()
        if execution_id:
            rows=db.execute(
                select(TokenConsumptionAllocation,TokenValueLot)
                .join(TokenValueLot,TokenValueLot.id==TokenConsumptionAllocation.lot_id)
                .where(TokenConsumptionAllocation.execution_id==execution_id)
                .order_by(TokenConsumptionAllocation.id)
            ).all()
            for allocation,lot in rows:
                available=max(int(allocation.tokens_allocated-allocation.tokens_reversed),0)
                if available:
                    segments.append((lot,available,"already_allocated"))
                    used_lot_ids.add(lot.id)
        lots=db.execute(
            select(TokenValueLot)
            .where(TokenValueLot.user_id==user_id,TokenValueLot.remaining_tokens>0)
            .order_by(TokenValueLot.created_at,TokenValueLot.id)
            .with_for_update()
        ).scalars().all()
        for lot in lots:
            segments.append((lot,int(lot.remaining_tokens),"fifo_remaining"))
        remaining=cost
        total_tokens=0
        charged=Decimal("0")
        profit=Decimal("0")
        capacity_total=Decimal("0")
        bags=[]
        partial_trace=False
        for lot,available,segment_source in segments:
            if remaining<=0: break
            if available<=0: continue
            snapshot=self._snapshot_for_lot(lot,fallback_profit_per_token_usd=fallback_profit_per_token_usd)
            paid=snapshot["paid_value_per_token"]
            effective_profit=snapshot["effective_profit_per_token"] if apply_profit else Decimal("0")
            capacity=paid-effective_profit if apply_profit else paid
            capacity=max(capacity,Decimal("0"))
            if capacity<=0:
                continue
            needed=int((remaining/capacity).to_integral_value(rounding=ROUND_CEILING))
            take=min(max(needed,1),available)
            provided=capacity*take
            row_charged=paid*take
            row_profit=effective_profit*take
            total_tokens+=take
            charged+=row_charged
            profit+=row_profit
            capacity_total+=provided
            remaining=max(Decimal("0"),remaining-provided)
            partial_trace=partial_trace or snapshot["snapshot_source"]=="legacy_current_rule_fallback" or lot.source=="legacy_untraced_balance"
            bags.append({
                "token_bag_id":lot.id,"source":lot.source,"reference_id":lot.reference_id,
                "tokens":take,"segment_source":segment_source,
                "paid_value_per_token_usd":float(paid),
                "effective_profit_per_token_usd":float(effective_profit),
                "infrastructure_capacity_per_token_usd":float(capacity),
                "infrastructure_capacity_used_usd":float(provided),
                "snapshot_source":snapshot["snapshot_source"],
            })
        if remaining>Decimal("0"):
            raise ConflictException(
                "The user's token bags do not contain enough funded infrastructure capacity for this execution."
            )
        surplus=max(Decimal("0"),capacity_total-cost)
        return {
            "tokens":total_tokens,"charged_usd":float(charged),
            "configured_profit_usd":float(profit),"rounding_surplus_usd":float(surplus),
            "infrastructure_capacity_usd":float(capacity_total),"bags":bags,
            "traceability_status":"partial" if partial_trace else "exact",
        }

    def allocate(self, db:Session, *, user_id:int, execution_id:str, tokens:int, token_transaction_id:int|None) -> None:
        remaining=max(int(tokens),0)
        if remaining<=0:return
        lots=db.execute(select(TokenValueLot).where(TokenValueLot.user_id==user_id,TokenValueLot.remaining_tokens>0).order_by(TokenValueLot.created_at,TokenValueLot.id).with_for_update()).scalars().all()
        for lot in lots:
            if remaining<=0:break
            take=min(remaining,lot.remaining_tokens)
            lot.remaining_tokens-=take
            if take > 0 and lot.status == "new":
                snapshot=self._snapshot_for_lot(lot)
                lot.status="active"
                lot.activated_at=utc_now()
                lot.commercial_profit_released=True
                lot.released_commercial_profit_usd=(snapshot["effective_profit_per_token"]*lot.original_tokens).quantize(Decimal("0.000001"))
            if lot.remaining_tokens <= 0 and lot.status not in {"expired","refunded"}:
                lot.status="exhausted"
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
            if lot:
                lot.remaining_tokens+=give
                if lot.status == "exhausted": lot.status="active" if lot.activated_at else "new"
                db.add(lot)
            db.add(allocation); remaining-=give
        db.flush()

    def execution_summary(self, db:Session, execution_id:str, expected_tokens:int|None=None) -> dict:
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
                    "infrastructure_capacity_per_token_usd":float(max(value-effective_per_token,Decimal("0"))),
                    "infrastructure_capacity_from_tokens_usd":0.0,
                    "cash_value_at_purchase_usd":0.0,
                    "coupon_code":metadata.get("coupon_code"),
                    "plan_name":metadata.get("plan_name"),
                }
                grouped[lot.id]=current
            current["tokens_used"]+=net
            current["profit_without_benefit_usd"]+=float(row_normal)
            current["benefit_given_usd"]+=float(row_discount)
            current["company_profit_usd"]+=float(row_net)
            current["infrastructure_capacity_from_tokens_usd"]+=float(max(value-effective_per_token,Decimal("0"))*net)
            current["cash_value_at_purchase_usd"]+=float(value*net)
        # Historical/cancelled executions may have all reservation allocations marked
        # as reversed even though billing finalized with a minimum non-zero token charge.
        # Rebuild a read-only FIFO presentation from the original rows; do not mutate lots.
        expected=max(int(expected_tokens or 0),0)
        if tokens == 0 and expected > 0 and rows:
            remaining_expected=expected
            grouped={}
            for allocation,lot in rows:
                if remaining_expected<=0:
                    break
                original=max(int(allocation.tokens_allocated or 0),0)
                take=min(original,remaining_expected)
                if take<=0:
                    continue
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
                value=Decimal(allocation.effective_token_value_usd or 0)
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
                row_normal=normal_per_token*take
                row_net=effective_per_token*take
                current["tokens_used"]+=take
                current["profit_without_benefit_usd"]+=float(row_normal)
                current["benefit_given_usd"]+=float(max(Decimal("0"),row_normal-row_net))
                current["company_profit_usd"]+=float(row_net)
                current["infrastructure_capacity_from_tokens_usd"]+=float(max(value-effective_per_token,Decimal("0"))*take)
                current["cash_value_at_purchase_usd"]+=float(value*take)
                tokens+=take
                cash_revenue+=value*take
                normal_profit+=row_normal
                discount_given+=max(Decimal("0"),row_normal-row_net)
                net_profit+=row_net
                legacy=legacy or lot.source=="legacy_untraced_balance"
                remaining_expected-=take
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
