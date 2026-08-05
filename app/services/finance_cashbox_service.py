from __future__ import annotations
import json
from datetime import timedelta
from decimal import Decimal
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.common.exceptions import ConflictException, NotFoundException
from app.common.time import utc_now
from app.models.finance_withdrawal import FinanceWithdrawal
from app.models.generation_financial_record import GenerationFinancialRecord
from app.models.system_setting import SystemSetting
from app.models.token_consumption_allocation import TokenConsumptionAllocation
from app.models.token_purchase import TokenPurchase
from app.models.token_value_lot import TokenValueLot
from app.models.user import User
from app.schemas.finance_cashbox import WithdrawalCreate
from app.services.token_value_ledger_service import token_value_ledger_service

D=Decimal
class FinanceCashboxService:
    EXPIRY_ENABLED='token_bag_expiration_enabled'; EXPIRY_DAYS='token_bag_expiration_days'
    def _meta(self, lot):
        try: return json.loads(lot.metadata_json or '{}')
        except Exception: return {}
    def _historical_bag_usage(self,db,lot_id):
        """Read-only compatibility for records created before cashbox lifecycle fields.

        Current executions are sourced from net token allocations. Older executions may
        have allocations fully reversed by legacy reconciliation while their immutable
        financial breakdown still proves that a bag paid tokens. This evidence blocks
        an unsafe refund and releases the bag's commercial profit, but never mutates the
        user's token balance.
        """
        tokens=0; generations=[]
        records=db.execute(
            select(GenerationFinancialRecord)
            .where(GenerationFinancialRecord.breakdown_json.is_not(None))
            .order_by(GenerationFinancialRecord.created_at)
        ).scalars().all()
        for rec in records:
            try: breakdown=json.loads(rec.breakdown_json or '{}')
            except Exception: continue
            bags=breakdown.get('token_bags_used') or breakdown.get('allocations') or []
            for bag in bags:
                try: bag_id=int(bag.get('token_bag_id') or 0)
                except (TypeError,ValueError): continue
                if bag_id != int(lot_id): continue
                used=max(int(bag.get('tokens_used') or bag.get('tokens') or 0),0)
                if used<=0: continue
                tokens += used
                generations.append({
                    'execution_id':rec.execution_id,
                    'tokens_used':used,
                    'created_at':rec.created_at,
                    'infrastructure_cost_usd':float(rec.infrastructure_cost_usd or 0),
                    'company_profit_usd':float(rec.gross_profit_usd or 0),
                    'rounding_surplus_usd':float(breakdown.get('rounding_surplus_for_company_usd') or breakdown.get('profit_rounding_surplus_usd') or 0),
                    'status':rec.status,
                    'historical_reconstruction':True,
                })
        return tokens,generations
    def expiration_settings(self,db):
        rows={x.key:x for x in db.execute(select(SystemSetting).where(SystemSetting.key.in_([self.EXPIRY_ENABLED,self.EXPIRY_DAYS]))).scalars()}
        return {'enabled': bool(rows.get(self.EXPIRY_ENABLED).value_boolean) if rows.get(self.EXPIRY_ENABLED) else True,'days': int(rows.get(self.EXPIRY_DAYS).value_integer or 730) if rows.get(self.EXPIRY_DAYS) else 730}
    def set_expiration_settings(self,db,*,enabled,days):
        specs=[(self.EXPIRY_ENABLED,'Caducidad de bolsas habilitada','boolean',enabled),(self.EXPIRY_DAYS,'Caducidad de bolsas en días','integer',days)]
        for key,label,typ,val in specs:
            row=db.execute(select(SystemSetting).where(SystemSetting.key==key)).scalar_one_or_none()
            if not row: row=SystemSetting(category='billing',key=key,label=label,value_type=typ,is_public=False,is_editable=True)
            if typ=='boolean': row.value_boolean=bool(val)
            else: row.value_integer=int(val)
            db.add(row)
        db.flush(); return self.expiration_settings(db)
    def ensure_expirations(self,db):
        cfg=self.expiration_settings(db); now=utc_now()
        lots=db.execute(select(TokenValueLot).where(TokenValueLot.remaining_tokens>0,TokenValueLot.status.notin_(['expired','refunded']))).scalars().all()
        changed=0
        for lot in lots:
            if cfg['enabled'] and not lot.expires_at: lot.expires_at=lot.created_at+timedelta(days=cfg['days']); db.add(lot)
            if cfg['enabled'] and lot.expires_at and lot.expires_at<=now:
                snap=token_value_ledger_service._snapshot_for_lot(lot)
                release=snap['infrastructure_capacity_per_token']*lot.remaining_tokens
                if not lot.commercial_profit_released:
                    release += snap['effective_profit_per_token']*lot.remaining_tokens
                    lot.released_commercial_profit_usd=(snap['effective_profit_per_token']*lot.original_tokens).quantize(D('0.000001'))
                lot.released_expiration_usd=D(str(release)); lot.remaining_tokens=0; lot.status='expired'; lot.expired_at=now
                lot.commercial_profit_released=True
                db.add(lot); changed+=1
        if changed: db.flush()
    def _bag_values(self,db,lot,user_email=None):
        m=self._meta(lot); snap=token_value_ledger_service._snapshot_for_lot(lot)
        consumed=max(lot.original_tokens-lot.remaining_tokens,0)
        allocations=db.execute(select(TokenConsumptionAllocation).where(TokenConsumptionAllocation.lot_id==lot.id)).scalars().all()
        net_alloc=sum(max(a.tokens_allocated-a.tokens_reversed,0) for a in allocations)
        historical_consumed,_=self._historical_bag_usage(db,lot.id) if net_alloc==0 else (0,[])
        consumed=max(consumed,net_alloc,historical_consumed)
        infra_used=D('0'); rounding=D('0')
        for a in allocations:
            if max(a.tokens_allocated-a.tokens_reversed,0)<=0: continue
            rec=db.execute(select(GenerationFinancialRecord).where(GenerationFinancialRecord.execution_id==a.execution_id)).scalar_one_or_none()
            if not rec: continue
            try: b=json.loads(rec.breakdown_json or '{}')
            except Exception: b={}
            bags=b.get('token_bags_used') or []
            total_cap=sum(D(str(x.get('infrastructure_capacity_from_tokens_usd') or 0)) for x in bags)
            this=next((x for x in bags if int(x.get('token_bag_id') or 0)==lot.id),None)
            if this and total_cap>0:
                share=D(str(this.get('infrastructure_capacity_from_tokens_usd') or 0))/total_cap
                infra_used += D(str(rec.infrastructure_cost_usd or 0))*share
                rounding += D(str(b.get('rounding_surplus_for_company_usd') or 0))*share
        total_profit=snap['effective_profit_per_token']*lot.original_tokens
        protected=snap['infrastructure_capacity_per_token']*lot.remaining_tokens
        if consumed > 0 and lot.status in ('new','active','exhausted') and not lot.commercial_profit_released:
            lot.status='exhausted' if lot.remaining_tokens <= 0 else 'active'
            lot.activated_at=lot.activated_at or lot.created_at
            lot.commercial_profit_released=True
            lot.released_commercial_profit_usd=total_profit.quantize(D('0.000001'))
            db.add(lot); db.flush()
        released=D(str(lot.released_commercial_profit_usd or 0))
        purchase=None
        try: purchase=db.get(TokenPurchase,int(lot.reference_id)) if lot.source in ('free_token_purchase','token_package','subscription','plan') and lot.reference_id else None
        except Exception: pass
        pstatus=getattr(purchase,'status',None)
        refundable=lot.status=='new' and consumed==0 and not lot.refunded_at and pstatus not in ('refunded','partially_refunded')
        reason='Reembolso total disponible: la bolsa no ha consumido tokens.' if refundable else ('No reembolsable: la bolsa ya consumió tokens.' if consumed else 'No reembolsable por el estado actual del pago o de la bolsa.')
        return {'id':lot.id,'user_id':lot.user_id,'user_email':user_email,'source':lot.source,'source_label':m.get('source_label') or m.get('plan_name') or m.get('package_name') or lot.source,'reference_id':lot.reference_id,'status':lot.status,'original_tokens':lot.original_tokens,'remaining_tokens':lot.remaining_tokens,'consumed_tokens':consumed,'amount_paid_usd':float(lot.amount_paid_usd or 0),'effective_token_value_usd':float(snap['paid_value_per_token']),'normal_profit_per_token_usd':float(snap['normal_profit_per_token']),'effective_profit_per_token_usd':float(snap['effective_profit_per_token']),'infrastructure_capacity_per_token_usd':float(snap['infrastructure_capacity_per_token']),'commercial_profit_total_usd':float(total_profit),'commercial_profit_released_usd':float(released),'protected_infrastructure_remaining_usd':float(protected),'infrastructure_used_usd':float(infra_used),'rounding_surplus_usd':float(rounding),'expiration_release_usd':float(lot.released_expiration_usd or 0),'coupon_code':m.get('coupon_code'),'plan_name':m.get('plan_name'),'payment_status':str(pstatus) if pstatus else None,'refundable':refundable,'refund_reason':reason,'activated_at':lot.activated_at,'expires_at':lot.expires_at,'expired_at':lot.expired_at,'created_at':lot.created_at}
    def list_bags(self,db,*,status=None,user_id=None,skip=0,limit=100):
        self.ensure_expirations(db); q=select(TokenValueLot,User.email).join(User,User.id==TokenValueLot.user_id)
        if status:q=q.where(TokenValueLot.status==status)
        if user_id:q=q.where(TokenValueLot.user_id==user_id)
        total=db.execute(select(func.count()).select_from(q.subquery())).scalar_one()
        rows=db.execute(q.order_by(TokenValueLot.created_at.desc()).offset(skip).limit(limit)).all()
        return {'items':[self._bag_values(db,l,e) for l,e in rows],'total':total}
    def detail(self,db,bag_id):
        self.ensure_expirations(db); row=db.execute(select(TokenValueLot,User.email).join(User,User.id==TokenValueLot.user_id).where(TokenValueLot.id==bag_id)).first()
        if not row: raise NotFoundException('Token bag not found.')
        lot,email=row; allocs=db.execute(select(TokenConsumptionAllocation).where(TokenConsumptionAllocation.lot_id==bag_id).order_by(TokenConsumptionAllocation.created_at.desc())).scalars().all()
        gens=[]
        for a in allocs:
            net=max(a.tokens_allocated-a.tokens_reversed,0)
            if not net: continue
            rec=db.execute(select(GenerationFinancialRecord).where(GenerationFinancialRecord.execution_id==a.execution_id)).scalar_one_or_none()
            b={}
            if rec:
                try:b=json.loads(rec.breakdown_json or '{}')
                except:pass
            gens.append({'execution_id':a.execution_id,'tokens_used':net,'created_at':a.created_at,'infrastructure_cost_usd':float(rec.infrastructure_cost_usd or 0) if rec else 0,'company_profit_usd':float(rec.gross_profit_usd or 0) if rec else 0,'rounding_surplus_usd':float(b.get('rounding_surplus_for_company_usd') or 0),'status':rec.status if rec else None,'historical_reconstruction':False})
        if not gens:
            _,gens=self._historical_bag_usage(db,lot.id)
        timeline=[{'type':'purchase','at':lot.created_at.isoformat(),'label':'Bolsa creada'}]
        if lot.activated_at:timeline.append({'type':'activation','at':lot.activated_at.isoformat(),'label':'Primer consumo: utilidad comercial liberada'})
        if lot.expired_at:timeline.append({'type':'expiration','at':lot.expired_at.isoformat(),'label':'Bolsa expirada y saldo restante liberado'})
        if lot.refunded_at:timeline.append({'type':'refund','at':lot.refunded_at.isoformat(),'label':'Bolsa reembolsada'})
        purchase_id=int(lot.reference_id) if lot.reference_id and str(lot.reference_id).isdigit() else None
        return {'bag':self._bag_values(db,lot,email),'generations':gens,'timeline':sorted(timeline,key=lambda x:x['at']),'purchase_id':purchase_id}
    def summary(self,db):
        self.ensure_expirations(db); lots=db.execute(select(TokenValueLot)).scalars().all(); values=[self._bag_values(db,l) for l in lots]
        released=sum(D(str(x['commercial_profit_released_usd'])) for x in values); protected=sum(D(str(x['protected_infrastructure_remaining_usd'])) for x in values); blocked=sum(D(str(x['commercial_profit_total_usd'])) for x in values if x['status']=='new'); rounding=sum(D(str(x['rounding_surplus_usd'])) for x in values); expir=sum(D(str(x['expiration_release_usd'])) for x in values); withdrawals=db.execute(select(func.coalesce(func.sum(FinanceWithdrawal.amount_usd),0))).scalar_one(); available=max(D('0'),released+rounding+expir-D(str(withdrawals)))
        return {'collected_usd':float(sum(D(str(x['amount_paid_usd'])) for x in values)),'available_usd':float(available),'protected_infrastructure_usd':float(protected),'blocked_profit_usd':float(blocked),'released_commercial_profit_usd':float(released),'rounding_and_operational_surplus_usd':float(rounding),'expiration_releases_usd':float(expir),'withdrawals_usd':float(withdrawals),'active_bags':sum(x['status']=='active' for x in values),'new_bags':sum(x['status']=='new' for x in values),'expired_bags':sum(x['status']=='expired' for x in values)}
    def withdrawals(self,db): return db.execute(select(FinanceWithdrawal).order_by(FinanceWithdrawal.withdrawn_at.desc())).scalars().all()
    def create_withdrawal(self,db,data,admin_id):
        available=D(str(self.summary(db)['available_usd'])); amount=D(str(data.amount_usd))
        if amount>available: raise ConflictException(f'Withdrawal exceeds available cash. Available: USD {available}.')
        row=FinanceWithdrawal(amount_usd=amount,currency='USD',beneficiary=data.beneficiary,concept=data.concept,method=data.method,proof_url=data.proof_url,notes=data.notes,created_by_user_id=admin_id,withdrawn_at=data.withdrawn_at or utc_now()); db.add(row); db.flush(); return row
finance_cashbox_service=FinanceCashboxService()
