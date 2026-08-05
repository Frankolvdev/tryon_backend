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
from app.models.token_package import TokenPackage
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
    def _generation_rows_for_bag(self,db,lot):
        """Return one consolidated row per execution for this bag.

        Historical billing can contain more than one allocation for the same execution
        (initial reservation plus final adjustment).  The immutable financial breakdown
        is the source of truth for presentation and prevents duplicated generations or
        repeating the full execution totals for every allocation row.
        """
        allocations=db.execute(
            select(TokenConsumptionAllocation)
            .where(TokenConsumptionAllocation.lot_id==lot.id)
            .order_by(TokenConsumptionAllocation.created_at,TokenConsumptionAllocation.id)
        ).scalars().all()
        by_execution={}
        for allocation in allocations:
            key=str(allocation.execution_id)
            item=by_execution.setdefault(key,{"allocations":[],"created_at":allocation.created_at})
            item["allocations"].append(allocation)
            if allocation.created_at and (not item["created_at"] or allocation.created_at<item["created_at"]):
                item["created_at"]=allocation.created_at
        rows=[]
        for execution_id,item in by_execution.items():
            rec=db.execute(
                select(GenerationFinancialRecord).where(GenerationFinancialRecord.execution_id==execution_id)
            ).scalar_one_or_none()
            breakdown={}
            if rec:
                try: breakdown=json.loads(rec.breakdown_json or '{}')
                except Exception: breakdown={}
            bag_parts=[
                x for x in (breakdown.get('token_bags_used') or [])
                if int(x.get('token_bag_id') or 0)==lot.id
            ]
            if bag_parts:
                tokens=sum(max(int(x.get('tokens_used') or x.get('tokens') or 0),0) for x in bag_parts)
                capacity=sum(D(str(x.get('infrastructure_capacity_from_tokens_usd') or x.get('infrastructure_capacity_used_usd') or 0)) for x in bag_parts)
                commercial=sum(D(str(x.get('company_profit_usd') or 0)) for x in bag_parts)
                all_parts=breakdown.get('token_bags_used') or []
                total_capacity=sum(D(str(x.get('infrastructure_capacity_from_tokens_usd') or x.get('infrastructure_capacity_used_usd') or 0)) for x in all_parts)
                share=(capacity/total_capacity) if total_capacity>0 else D('0')
                infra=D(str(rec.infrastructure_cost_usd or 0))*share if rec else D('0')
                rounding=D(str(breakdown.get('rounding_surplus_for_company_usd') or 0))*share
            else:
                # Legacy fallback: consolidate net allocations for the execution.
                tokens=sum(max(int(a.tokens_allocated or 0)-int(a.tokens_reversed or 0),0) for a in item['allocations'])
                snap=token_value_ledger_service._snapshot_for_lot(lot)
                capacity=snap['infrastructure_capacity_per_token']*tokens
                commercial=snap['effective_profit_per_token']*tokens
                infra=D('0'); rounding=D('0')
                if rec and tokens>0:
                    infra=D(str(rec.infrastructure_cost_usd or 0))
                    rounding=D(str(breakdown.get('rounding_surplus_for_company_usd') or 0))
            if tokens<=0:
                continue
            rows.append({
                'execution_id':execution_id,
                'tokens_used':tokens,
                'created_at':getattr(rec,'created_at',None) or item['created_at'],
                'infrastructure_cost_usd':float(infra),
                'commercial_profit_usd':float(commercial),
                'rounding_surplus_usd':float(rounding),
                'company_profit_usd':float(commercial+rounding),
                'status':rec.status if rec else None,
            })
        rows.sort(key=lambda x:x['created_at'] or utc_now(),reverse=True)
        return rows

    def _bag_values(self,db,lot,user_email=None):
        m=self._meta(lot); snap=token_value_ledger_service._snapshot_for_lot(lot)
        generation_rows=self._generation_rows_for_bag(db,lot)
        historical_consumed=sum(int(x['tokens_used']) for x in generation_rows)
        consumed=max(int(lot.original_tokens or 0)-int(lot.remaining_tokens or 0),historical_consumed,0)
        infra_used=sum(D(str(x['infrastructure_cost_usd'])) for x in generation_rows)
        rounding=sum(D(str(x['rounding_surplus_usd'])) for x in generation_rows)
        total_profit=snap['effective_profit_per_token']*lot.original_tokens
        # Repair both modern and historical bags.  Older flows sometimes set the
        # boolean flag but left the released amount at zero.
        released_amount=D(str(lot.released_commercial_profit_usd or 0))
        if consumed>0 and lot.status not in ('expired','refunded'):
            lot.status='exhausted' if lot.remaining_tokens<=0 else 'active'
            lot.activated_at=lot.activated_at or lot.created_at
            if (not lot.commercial_profit_released) or released_amount<=0:
                lot.commercial_profit_released=True
                lot.released_commercial_profit_usd=total_profit.quantize(D('0.000001'))
                released_amount=D(str(lot.released_commercial_profit_usd))
            db.add(lot); db.flush()
        protected=snap['infrastructure_capacity_per_token']*lot.remaining_tokens
        released=D(str(lot.released_commercial_profit_usd or 0))
        purchase=None
        try: purchase=db.get(TokenPurchase,int(lot.reference_id)) if lot.source in ('free_token_purchase','token_package','subscription','plan') and lot.reference_id else None
        except Exception: pass
        pstatus=getattr(purchase,'status',None)
        package_name=m.get('package_name') or m.get('token_package_name')
        if not package_name and purchase and getattr(purchase,'token_package_id',None):
            package=db.get(TokenPackage,purchase.token_package_id)
            package_name=getattr(package,'name',None)
        refundable=lot.status=='new' and consumed==0 and not lot.refunded_at and pstatus not in ('refunded','partially_refunded')
        reason='Reembolso total disponible: todavía no se ha usado ningún token de esta bolsa.' if refundable else ('No se puede reembolsar automáticamente porque esta bolsa ya se utilizó.' if consumed else 'No se puede reembolsar por el estado actual del pago o de la bolsa.')
        realized_extra=max(rounding,D('0'))
        total_available=released+realized_extra+D(str(lot.released_expiration_usd or 0))
        discount=D(str(m.get('profit_discount_percent') or 0))
        benefit_source=m.get('benefit_source') or ('coupon' if m.get('coupon_code') else ('plan' if m.get('plan_name') else ('package' if package_name else None)))
        benefit_label=m.get('benefit_label') or m.get('coupon_code') or m.get('plan_name') or package_name
        return {'id':lot.id,'user_id':lot.user_id,'user_email':user_email,'source':lot.source,'source_label':m.get('source_label') or m.get('plan_name') or package_name or lot.source,'reference_id':lot.reference_id,'status':lot.status,'original_tokens':lot.original_tokens,'remaining_tokens':lot.remaining_tokens,'consumed_tokens':consumed,'amount_paid_usd':float(lot.amount_paid_usd or 0),'effective_token_value_usd':float(snap['paid_value_per_token']),'normal_profit_per_token_usd':float(snap['normal_profit_per_token']),'effective_profit_per_token_usd':float(snap['effective_profit_per_token']),'infrastructure_capacity_per_token_usd':float(snap['infrastructure_capacity_per_token']),'commercial_profit_total_usd':float(total_profit),'commercial_profit_released_usd':float(released),'realized_extra_profit_usd':float(realized_extra),'total_available_from_bag_usd':float(total_available),'protected_infrastructure_remaining_usd':float(protected),'infrastructure_used_usd':float(infra_used),'rounding_surplus_usd':float(rounding),'expiration_release_usd':float(lot.released_expiration_usd or 0),'coupon_code':m.get('coupon_code'),'plan_name':m.get('plan_name'),'package_name':package_name,'benefit_source':benefit_source,'benefit_label':benefit_label,'profit_discount_percent':float(discount),'snapshot_version':int(m.get('financial_snapshot_version')) if str(m.get('financial_snapshot_version') or '').isdigit() else None,'snapshot_source':snap.get('snapshot_source'),'payment_status':str(pstatus) if pstatus else None,'refundable':refundable,'refund_reason':reason,'activated_at':lot.activated_at,'expires_at':lot.expires_at,'expired_at':lot.expired_at,'created_at':lot.created_at}
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
        lot,email=row
        bag=self._bag_values(db,lot,email)
        gens=self._generation_rows_for_bag(db,lot)
        timeline=[{'type':'purchase','at':lot.created_at.isoformat(),'label':'Se creó la bolsa'}]
        if lot.activated_at:timeline.append({'type':'activation','at':lot.activated_at.isoformat(),'label':'Se usó por primera vez y su ganancia quedó disponible'})
        if lot.expired_at:timeline.append({'type':'expiration','at':lot.expired_at.isoformat(),'label':'La bolsa venció y el dinero restante se liberó'})
        if lot.refunded_at:timeline.append({'type':'refund','at':lot.refunded_at.isoformat(),'label':'La bolsa fue reembolsada'})
        purchase_id=int(lot.reference_id) if lot.reference_id and str(lot.reference_id).isdigit() else None
        return {'bag':bag,'generations':gens,'timeline':sorted(timeline,key=lambda x:x['at']),'purchase_id':purchase_id}
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
