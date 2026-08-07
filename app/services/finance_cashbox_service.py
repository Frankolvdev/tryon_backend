from __future__ import annotations
import json
from datetime import timedelta
from decimal import Decimal
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.common.exceptions import ConflictException, ForbiddenException, NotFoundException
from app.common.enums import TokenTransactionType
from app.common.time import utc_now
from app.core.config import settings
from app.models.finance_withdrawal import FinanceWithdrawal
from app.models.infrastructure_funding import (
    InfrastructureFundingMovement,
    InfrastructureFundingAllocation,
    InfrastructureProviderCreditRelease,
)
from app.models.generation_financial_record import GenerationFinancialRecord
from app.models.system_setting import SystemSetting
from app.models.token_consumption_allocation import TokenConsumptionAllocation
from app.models.token_purchase import TokenPurchase
from app.models.token_package import TokenPackage
from app.models.token_value_lot import TokenValueLot
from app.models.token_transaction import TokenTransaction
from app.models.user import User
from app.schemas.finance_cashbox import WithdrawalCreate, InfrastructureFundingCreate
from app.services.token_value_ledger_service import token_value_ledger_service
from app.services.token_bag_expiration_accounting import calculate_token_bag_expiration_amounts
from app.services.infrastructure_cashbox_accounting import (
    calculate_infrastructure_funding_state,
    calculate_expiration_infrastructure_split,
)
from app.services.pending_recovery_service import pending_recovery_service
from app.services.promotional_credit_service import promotional_credit_service
from app.services.operational_cashbox_service import operational_cashbox_service

D=Decimal
class FinanceCashboxService:
    EXPIRY_ENABLED='token_bag_expiration_enabled'; EXPIRY_DAYS='token_bag_expiration_days'
    def _meta(self, lot):
        try: return json.loads(lot.metadata_json or '{}')
        except Exception: return {}
    def expiration_settings(self,db):
        rows={x.key:x for x in db.execute(select(SystemSetting).where(SystemSetting.key.in_([self.EXPIRY_ENABLED,self.EXPIRY_DAYS]))).scalars()}
        simulation_enabled=(
            settings.APP_ENV.lower() not in {'production','prod'}
            and bool(settings.TEST_FORCE_TOKEN_BAG_EXPIRATION)
        )
        return {
            'enabled': bool(rows.get(self.EXPIRY_ENABLED).value_boolean) if rows.get(self.EXPIRY_ENABLED) else True,
            'days': int(rows.get(self.EXPIRY_DAYS).value_integer or 730) if rows.get(self.EXPIRY_DAYS) else 730,
            'simulation_enabled': simulation_enabled,
        }
    def set_expiration_settings(self,db,*,enabled,days):
        specs=[(self.EXPIRY_ENABLED,'Caducidad de bolsas habilitada','boolean',enabled),(self.EXPIRY_DAYS,'Caducidad de bolsas en días','integer',days)]
        for key,label,typ,val in specs:
            row=db.execute(select(SystemSetting).where(SystemSetting.key==key)).scalar_one_or_none()
            if not row: row=SystemSetting(category='billing',key=key,label=label,value_type=typ,is_public=False,is_editable=True)
            if typ=='boolean': row.value_boolean=bool(val)
            else: row.value_integer=int(val)
            db.add(row)
        db.flush(); return self.expiration_settings(db)

    def _funding_rows_for_lot(self, db: Session, lot_id: int):
        return db.execute(
            select(InfrastructureFundingAllocation, InfrastructureFundingMovement)
            .join(
                InfrastructureFundingMovement,
                InfrastructureFundingMovement.id == InfrastructureFundingAllocation.movement_id,
            )
            .where(InfrastructureFundingAllocation.lot_id == lot_id)
            .order_by(
                InfrastructureFundingAllocation.created_at,
                InfrastructureFundingAllocation.id,
            )
        ).all()

    def _infrastructure_used_by_provider(self, db: Session, lot: TokenValueLot) -> dict[str, D]:
        result: dict[str, D] = {}
        for row in self._generation_rows_for_bag(db, lot):
            provider = str(row.get("provider") or "unknown").lower()
            result[provider] = result.get(provider, D("0")) + D(
                str(row.get("infrastructure_cost_usd") or 0)
            )
        return result



    def _funding_state_for_lot(
        self,
        db: Session,
        lot: TokenValueLot,
        *,
        protected: D | None = None,
        infrastructure_used: D | None = None,
    ) -> dict:
        if protected is None:
            snap = token_value_ledger_service._snapshot_for_lot(lot)
            protected = (
                snap["infrastructure_capacity_per_token"]
                * max(int(lot.remaining_tokens or 0), 0)
            )

        funding_rows = self._funding_rows_for_lot(db, lot.id)
        funded_by_provider: dict[str, D] = {}
        for allocation, movement in funding_rows:
            provider = str(movement.provider or "unknown").lower()
            funded_by_provider[provider] = funded_by_provider.get(provider, D("0")) + D(
                str(allocation.amount_usd or 0)
            )

        used_by_provider = self._infrastructure_used_by_provider(db, lot)
        state = calculate_infrastructure_funding_state(
            protected_reserve_usd=D(str(protected or 0)),
            infrastructure_used_by_provider_usd=used_by_provider,
            funded_by_provider_usd=funded_by_provider,
        )
        released_credit = db.execute(
            select(
                func.coalesce(
                    func.sum(InfrastructureProviderCreditRelease.amount_usd), 0
                )
            ).where(InfrastructureProviderCreditRelease.lot_id == lot.id)
        ).scalar_one()
        return {
            "funded_usd": state.funded_usd,
            "unfunded_usd": state.unfunded_usd,
            "unfunded_cost_usd": state.unfunded_provider_cost_usd,
            "unfunded_future_reserve_usd": state.unfunded_future_reserve_usd,
            "provider_excess_credit_usd": state.provider_excess_credit_usd,
            "provider_credit_released_usd": D(str(released_credit or 0)),
            "funded_by_provider": funded_by_provider,
            "used_by_provider": used_by_provider,
            "funding_rows": funding_rows,
        }


    def _split_expiration_infrastructure(
        self,
        db: Session,
        lot: TokenValueLot,
        *,
        protected_reserve: D,
    ) -> dict:
        """Split expiring reserve into bank cash and already-funded provider credit."""
        protected = max(D(str(protected_reserve or 0)), D("0")).quantize(D("0.000001"))
        if protected <= 0:
            return {
                "cash_release_usd": D("0"),
                "provider_credit_release_usd": D("0"),
                "provider_credit_by_provider": {},
            }

        existing = db.execute(
            select(InfrastructureProviderCreditRelease).where(
                InfrastructureProviderCreditRelease.lot_id == lot.id
            )
        ).scalars().all()
        if existing:
            by_provider: dict[str, D] = {}
            for row in existing:
                by_provider[row.provider] = by_provider.get(row.provider, D("0")) + D(
                    str(row.amount_usd or 0)
                )
            credit = min(sum(by_provider.values()), protected)
            return {
                "cash_release_usd": max(protected - credit, D("0")),
                "provider_credit_release_usd": credit,
                "provider_credit_by_provider": by_provider,
            }

        funding_rows = self._funding_rows_for_lot(db, lot.id)
        split = calculate_expiration_infrastructure_split(
            protected_reserve_usd=protected,
            infrastructure_used_by_provider_usd=self._infrastructure_used_by_provider(db, lot),
            funding_allocations=[
                (
                    allocation.id,
                    str(movement.provider or "unknown").lower(),
                    D(str(allocation.amount_usd or 0)),
                )
                for allocation, movement in funding_rows
            ],
        )
        by_provider: dict[str, D] = {}
        for release in split.credit_allocations:
            db.add(
                InfrastructureProviderCreditRelease(
                    lot_id=lot.id,
                    funding_allocation_id=release.funding_allocation_id,
                    provider=release.provider,
                    amount_usd=release.amount_usd,
                    reason="token_bag_expiration",
                )
            )
            by_provider[release.provider] = (
                by_provider.get(release.provider, D("0")) + release.amount_usd
            )
        return {
            "cash_release_usd": split.cash_release_usd,
            "provider_credit_release_usd": split.provider_credit_release_usd,
            "provider_credit_by_provider": by_provider,
        }

    def _expire_lot(self,db,lot,*,expired_at):
        if lot.status in ('expired','refunded') or int(lot.remaining_tokens or 0)<=0:
            return None
        snap=token_value_ledger_service._snapshot_for_lot(lot)
        expired_tokens=int(lot.remaining_tokens or 0)
        amounts=calculate_token_bag_expiration_amounts(
            original_tokens=int(lot.original_tokens or 0),
            remaining_tokens=expired_tokens,
            infrastructure_capacity_per_token_usd=snap['infrastructure_capacity_per_token'],
            effective_profit_per_token_usd=snap['effective_profit_per_token'],
            commercial_profit_released=bool(lot.commercial_profit_released),
            released_commercial_profit_usd=D(str(lot.released_commercial_profit_usd or 0)),
        )
        # Commercial profit and unused infrastructure are separate buckets.
        # Mixing both into released_expiration_usd makes Caja add the profit twice
        # when a never-used bag expires.
        lot.released_commercial_profit_usd=amounts.commercial_profit_released_usd
        lot.commercial_profit_released=True
        if lot.source == "promotional_credit":
            promotional_return = promotional_credit_service.return_for_expired_lot(
                db, lot=lot, remaining_tokens=expired_tokens,
            )
            # Provider-sponsored credits are never company revenue. Expiration
            # restores their unused reserve to the promotional pool instead of
            # moving a cent to Caja verde or the commercial IA cashbox.
            lot.released_commercial_profit_usd=D("0")
            lot.commercial_profit_released=True
            lot.released_expiration_usd=D("0")
            expiration_split={
                "cash_release_usd":D("0"),
                "provider_credit_release_usd":D("0"),
                "provider_credit_by_provider":{},
            }
        else:
            promotional_return=D("0")
            expiration_split=self._split_expiration_infrastructure(
                db,
                lot,
                protected_reserve=amounts.infrastructure_reserve_released_usd,
            )
            # Only cash that remains outside providers can become withdrawable profit.
            # Already-funded money remains provider credit and is never counted in Caja verde.
            lot.released_expiration_usd=expiration_split["cash_release_usd"]
        infrastructure_release=amounts.infrastructure_reserve_released_usd

        # Expiration must remove the same tokens from the user's wallet. Older
        # code zeroed only the lot, which could leave spendable balance behind
        # and later recreate it as legacy/untraced tokens. Keep wallet and bag
        # ledger atomic under the same database transaction.
        user=db.execute(
            select(User).where(User.id==lot.user_id).with_for_update()
        ).scalar_one_or_none()
        if user is not None:
            before=max(int(user.token_balance or 0),0)
            removed=min(before,expired_tokens)
            user.token_balance=before-removed
            db.add(user)
            if removed>0:
                db.add(TokenTransaction(
                    user_id=user.id,transaction_type=TokenTransactionType.DEBIT.value,
                    amount=-removed,balance_after=user.token_balance,
                    source='token_bag_expiration',reference_id=str(lot.id),
                    description=f'{removed} token(s) expired from token bag #{lot.id}.',
                ))

        # A never-used commercial bag becomes non-refundable at expiration.
        # Release only its frozen operating component; historical bags with a
        # zero component remain untouched. Promotional credits contribute zero.
        operational_cashbox_service.release_on_expiration(
            lot, expired_tokens=expired_tokens
        )

        lot.remaining_tokens=0
        lot.status='expired'
        lot.expired_at=expired_at
        db.add(lot)
        return {
            'expired_tokens': expired_tokens,
            'commercial_profit_released_usd': D(str(lot.released_commercial_profit_usd or 0)),
            'infrastructure_reserve_released_usd': infrastructure_release,
            'infrastructure_cash_released_usd': expiration_split["cash_release_usd"],
            'provider_credit_released_usd': expiration_split["provider_credit_release_usd"],
            'provider_credit_released_by_provider': expiration_split["provider_credit_by_provider"],
            'promotional_credit_returned_usd': promotional_return,
        }

    def ensure_expirations(self,db):
        cfg=self.expiration_settings(db); now=utc_now()
        lots=db.execute(
            select(TokenValueLot)
            .where(
                TokenValueLot.remaining_tokens>0,
                TokenValueLot.status.notin_(['expired','refunded']),
            )
            .order_by(TokenValueLot.created_at,TokenValueLot.id)
            .with_for_update()
        ).scalars().all()
        changed=0
        for lot in lots:
            if cfg['enabled'] and not lot.expires_at:
                lot.expires_at=lot.created_at+timedelta(days=cfg['days']); db.add(lot)
            if cfg['enabled'] and lot.expires_at and lot.expires_at<=now:
                if self._expire_lot(db,lot,expired_at=now): changed+=1
        if changed: db.flush()

    def simulate_expiration(self,db,bag_id):
        if settings.APP_ENV.lower() in {'production','prod'} or not settings.TEST_FORCE_TOKEN_BAG_EXPIRATION:
            raise ForbiddenException('Token bag expiration simulation is disabled.')
        lot=db.execute(
            select(TokenValueLot)
            .where(TokenValueLot.id==bag_id)
            .with_for_update()
        ).scalar_one_or_none()
        if not lot: raise NotFoundException('Token bag not found.')
        if lot.status in ('expired','refunded'):
            raise ConflictException('This token bag cannot be simulated in its current status.')
        if int(lot.remaining_tokens or 0)<=0:
            raise ConflictException('An exhausted token bag has no remaining tokens to expire.')
        previous_status=str(lot.status)
        now=utc_now()
        lot.expires_at=now
        result=self._expire_lot(db,lot,expired_at=now)
        db.flush()
        bag=self._bag_values(db,lot)
        return {
            'bag_id': lot.id,
            'previous_status': previous_status,
            'current_status': lot.status,
            'expired_tokens': int(result['expired_tokens']),
            'commercial_profit_released_usd': float(result['commercial_profit_released_usd']),
            'infrastructure_reserve_released_usd': float(result['infrastructure_reserve_released_usd']),
            'infrastructure_cash_released_usd': float(result['infrastructure_cash_released_usd']),
            'provider_credit_released_usd': float(result['provider_credit_released_usd']),
            'provider_credit_released_by_provider': {
                provider: float(amount)
                for provider, amount in result['provider_credit_released_by_provider'].items()
            },
            'promotional_credit_returned_usd': float(result.get('promotional_credit_returned_usd') or 0),
            'total_available_from_bag_usd': float(bag['total_available_from_bag_usd']),
            'expires_at': lot.expires_at,
            'expired_at': lot.expired_at,
        }
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
                'provider': str(breakdown.get('provider') or 'unknown').lower(),
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
        # Repair only the unmistakable historical double-count signature: the
        # expiration bucket can never exceed the complete AI reserve of the bag.
        # This leaves valid partially-used historical bags untouched.
        if lot.status=='expired':
            max_expiration_release=(
                snap['infrastructure_capacity_per_token']*int(lot.original_tokens or 0)
            ).quantize(D('0.000001'))
            current_expiration_release=D(str(lot.released_expiration_usd or 0))
            if current_expiration_release>max_expiration_release:
                lot.released_expiration_usd=max_expiration_release
                db.add(lot); db.flush()
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
        funding_state=self._funding_state_for_lot(
            db,
            lot,
            protected=protected,
            infrastructure_used=infra_used,
        )
        provider_rounding_credit=min(
            max(rounding,D('0')),
            max(D(str(funding_state['provider_excess_credit_usd'])),D('0')),
        )
        cash_rounding=max(rounding-provider_rounding_credit,D('0'))
        released=D(str(lot.released_commercial_profit_usd or 0))
        purchase=None
        try: purchase=db.get(TokenPurchase,int(lot.reference_id)) if lot.source in ('free_token_purchase','token_package','subscription','plan') and lot.reference_id else None
        except Exception: pass
        pstatus=getattr(purchase,'status',None)
        package_name=m.get('package_name') or m.get('token_package_name')
        if not package_name and purchase and getattr(purchase,'token_package_id',None):
            package=db.get(TokenPackage,purchase.token_package_id)
            package_name=getattr(package,'name',None)
        has_infrastructure_funding=D(str(funding_state['funded_usd']))>0
        refundable=lot.status=='new' and consumed==0 and not lot.refunded_at and pstatus not in ('refunded','partially_refunded') and not has_infrastructure_funding
        reason=(
            'Reembolso total disponible: todavía no se ha usado ningún token de esta bolsa.'
            if refundable
            else (
                'No se puede reembolsar automáticamente porque parte de la reserva de IA ya fue fondeada a un proveedor.'
                if has_infrastructure_funding
                else (
                    'No se puede reembolsar automáticamente porque esta bolsa ya se utilizó.'
                    if consumed
                    else 'No se puede reembolsar por el estado actual del pago o de la bolsa.'
                )
            )
        )
        realized_extra=cash_rounding
        total_available=released+realized_extra+D(str(lot.released_expiration_usd or 0))
        discount=D(str(m.get('profit_discount_percent') or 0))
        benefit_source=m.get('benefit_source') or ('coupon' if m.get('coupon_code') else ('plan' if m.get('plan_name') else ('package' if package_name else None)))
        benefit_label=m.get('benefit_label') or m.get('coupon_code') or m.get('plan_name') or package_name
        return {'id':lot.id,'user_id':lot.user_id,'user_email':user_email,'source':lot.source,'source_label':m.get('source_label') or m.get('plan_name') or package_name or lot.source,'reference_id':lot.reference_id,'status':lot.status,'original_tokens':lot.original_tokens,'remaining_tokens':lot.remaining_tokens,'consumed_tokens':consumed,'amount_paid_usd':float(lot.amount_paid_usd or 0),'effective_token_value_usd':float(snap['paid_value_per_token']),'normal_profit_per_token_usd':float(snap['normal_profit_per_token']),'effective_profit_per_token_usd':float(snap['effective_profit_per_token']),'infrastructure_capacity_per_token_usd':float(snap['infrastructure_capacity_per_token']),'operational_reserve_per_token_usd':float(snap.get('operational_reserve_per_token') or 0),'operational_reserve_total_usd':float(D(str(snap.get('operational_reserve_per_token') or 0))*max(int(lot.original_tokens or 0),0)),'operational_reserve_released_usd':float(getattr(lot,'released_operational_reserve_usd',0) or 0),'commercial_profit_total_usd':float(total_profit),'commercial_profit_released_usd':float(released),'realized_extra_profit_usd':float(realized_extra),'total_available_from_bag_usd':float(total_available),'protected_infrastructure_remaining_usd':float(protected),'infrastructure_used_usd':float(infra_used),'infrastructure_funded_usd':float(funding_state['funded_usd']),'infrastructure_unfunded_usd':float(funding_state['unfunded_usd']),'provider_credit_released_usd':float(funding_state['provider_credit_released_usd']),'rounding_surplus_usd':float(cash_rounding),'rounding_surplus_total_usd':float(max(rounding,D('0'))),'provider_rounding_credit_usd':float(provider_rounding_credit),'expiration_release_usd':float(lot.released_expiration_usd or 0),'coupon_code':m.get('coupon_code'),'plan_name':m.get('plan_name'),'package_name':package_name,'benefit_source':benefit_source,'benefit_label':benefit_label,'profit_discount_percent':float(discount),'snapshot_version':int(m.get('financial_snapshot_version')) if str(m.get('financial_snapshot_version') or '').isdigit() else None,'snapshot_source':snap.get('snapshot_source'),'payment_status':str(pstatus) if pstatus else None,'refundable':refundable,'refund_reason':reason,'activated_at':lot.activated_at,'expires_at':lot.expires_at,'expired_at':lot.expired_at,'created_at':lot.created_at}
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
        for allocation,movement in self._funding_rows_for_lot(db,lot.id):
            timeline.append({
                'type':'infrastructure_funding',
                'at':movement.funded_at.isoformat(),
                'label':f'Se fondearon USD {D(str(allocation.amount_usd or 0))} a {movement.provider} desde esta bolsa',
            })
        credit_releases=db.execute(
            select(InfrastructureProviderCreditRelease)
            .where(InfrastructureProviderCreditRelease.lot_id==lot.id)
            .order_by(InfrastructureProviderCreditRelease.created_at,InfrastructureProviderCreditRelease.id)
        ).scalars().all()
        for release in credit_releases:
            timeline.append({
                'type':'provider_credit_release',
                'at':release.created_at.isoformat(),
                'label':f'USD {D(str(release.amount_usd or 0))} quedó como crédito liberado en {release.provider}',
            })
        if lot.expired_at:timeline.append({'type':'expiration','at':lot.expired_at.isoformat(),'label':'La bolsa venció; solo el efectivo no fondeado pasó a utilidad'})
        if lot.refunded_at:timeline.append({'type':'refund','at':lot.refunded_at.isoformat(),'label':'La bolsa fue reembolsada'})
        purchase_id=int(lot.reference_id) if lot.reference_id and str(lot.reference_id).isdigit() else None
        return {'bag':bag,'generations':gens,'timeline':sorted(timeline,key=lambda x:x['at']),'purchase_id':purchase_id}

    def _provider_costs(self, db: Session, lots: list[TokenValueLot]) -> dict[str, D]:
        costs: dict[str, D] = {}
        for lot in lots:
            for row in self._generation_rows_for_bag(db, lot):
                provider = str(row.get("provider") or "unknown").lower()
                costs[provider] = costs.get(provider, D("0")) + D(
                    str(row.get("infrastructure_cost_usd") or 0)
                )
        return costs

    def _provider_funding_totals(self, db: Session) -> dict[str, D]:
        rows = db.execute(
            select(
                InfrastructureFundingMovement.provider,
                func.coalesce(func.sum(InfrastructureFundingMovement.amount_usd), 0),
            ).group_by(InfrastructureFundingMovement.provider)
        ).all()
        return {
            str(provider or "unknown").lower(): D(str(amount or 0))
            for provider, amount in rows
        }

    def _provider_credit_release_totals(self, db: Session) -> dict[str, D]:
        rows = db.execute(
            select(
                InfrastructureProviderCreditRelease.provider,
                func.coalesce(func.sum(InfrastructureProviderCreditRelease.amount_usd), 0),
            ).group_by(InfrastructureProviderCreditRelease.provider)
        ).all()
        return {
            str(provider or "unknown").lower(): D(str(amount or 0))
            for provider, amount in rows
        }

    def _funding_response(self, db: Session, movement: InfrastructureFundingMovement) -> dict:
        allocations = db.execute(
            select(InfrastructureFundingAllocation)
            .where(InfrastructureFundingAllocation.movement_id == movement.id)
            .order_by(InfrastructureFundingAllocation.id)
        ).scalars().all()
        return {
            "id": movement.id,
            "amount_usd": float(movement.amount_usd or 0),
            "currency": movement.currency,
            "provider": movement.provider,
            "beneficiary": movement.beneficiary,
            "concept": movement.concept,
            "method": movement.method,
            "proof_url": movement.proof_url,
            "notes": movement.notes,
            "created_by_user_id": movement.created_by_user_id,
            "funded_at": movement.funded_at,
            "created_at": movement.created_at,
            "allocations": [
                {
                    "id": allocation.id,
                    "lot_id": allocation.lot_id,
                    "amount_usd": float(allocation.amount_usd or 0),
                }
                for allocation in allocations
            ],
        }

    def infrastructure_fundings(self, db: Session) -> list[dict]:
        movements = db.execute(
            select(InfrastructureFundingMovement).order_by(
                InfrastructureFundingMovement.funded_at.desc(),
                InfrastructureFundingMovement.id.desc(),
            )
        ).scalars().all()
        return [self._funding_response(db, movement) for movement in movements]

    def create_infrastructure_funding(
        self,
        db: Session,
        data: InfrastructureFundingCreate,
        admin_id: int,
    ) -> dict:
        self.ensure_expirations(db)
        amount = D(str(data.amount_usd)).quantize(D("0.000001"))
        if amount <= 0:
            raise ConflictException("Infrastructure funding amount must be positive.")

        provider = str(data.provider or "").strip().lower()
        # Lock lots so two simultaneous funding registrations cannot allocate the same
        # infrastructure cash twice.
        lots = db.execute(
            select(TokenValueLot)
            .where(TokenValueLot.status != "refunded")
            .order_by(TokenValueLot.created_at, TokenValueLot.id)
            .with_for_update()
        ).scalars().all()

        candidates: list[tuple[TokenValueLot, D]] = []
        available = D("0")
        for lot in lots:
            if lot.source == "promotional_credit":
                continue
            snap = token_value_ledger_service._snapshot_for_lot(lot)
            protected = (
                snap["infrastructure_capacity_per_token"]
                * max(int(lot.remaining_tokens or 0), 0)
            )
            infra_used = sum(
                D(str(row.get("infrastructure_cost_usd") or 0))
                for row in self._generation_rows_for_bag(db, lot)
            )
            state = self._funding_state_for_lot(
                db,
                lot,
                protected=protected,
                infrastructure_used=infra_used,
            )
            provider_unfunded_cost = max(
                D(str(state["used_by_provider"].get(provider, D("0"))))
                - D(str(state["funded_by_provider"].get(provider, D("0")))),
                D("0"),
            )
            fundable = max(
                provider_unfunded_cost
                + D(str(state["unfunded_future_reserve_usd"])),
                D("0"),
            ).quantize(D("0.000001"))
            if fundable > 0:
                candidates.append((lot, fundable))
                available += fundable

        if amount > available:
            raise ConflictException(
                f"Infrastructure funding exceeds cash assignable to {provider}. Available: USD {available}."
            )

        movement = InfrastructureFundingMovement(
            amount_usd=amount,
            currency="USD",
            provider=provider,
            beneficiary=data.beneficiary,
            concept=data.concept,
            method=data.method,
            proof_url=data.proof_url,
            notes=data.notes,
            created_by_user_id=admin_id,
            funded_at=data.funded_at or utc_now(),
        )
        db.add(movement)
        db.flush()

        remaining = amount
        for lot, fundable in candidates:
            take = min(remaining, fundable).quantize(D("0.000001"))
            if take <= 0:
                continue
            db.add(
                InfrastructureFundingAllocation(
                    movement_id=movement.id,
                    lot_id=lot.id,
                    amount_usd=take,
                )
            )
            remaining -= take
            if remaining <= 0:
                break

        if remaining > D("0.000001"):
            raise ConflictException(
                "Infrastructure funding could not be fully allocated to token bags."
            )
        db.flush()
        return self._funding_response(db, movement)

    def summary(self,db):
        self.ensure_expirations(db)
        lots=db.execute(select(TokenValueLot)).scalars().all()
        commercial_lots=[lot for lot in lots if lot.source != "promotional_credit"]
        values=[self._bag_values(db,l) for l in commercial_lots]
        released=sum(D(str(x['commercial_profit_released_usd'])) for x in values)
        protected=sum(D(str(x['protected_infrastructure_remaining_usd'])) for x in values)
        blocked=sum(D(str(x['commercial_profit_total_usd'])) for x in values if x['status']=='new')
        rounding=sum(D(str(x['rounding_surplus_usd'])) for x in values)
        expir=sum(D(str(x['expiration_release_usd'])) for x in values)
        withdrawals=db.execute(select(func.coalesce(func.sum(FinanceWithdrawal.amount_usd),0))).scalar_one()
        available=max(D('0'),released+rounding+expir-D(str(withdrawals)))

        infrastructure_cash_available=sum(
            D(str(x['infrastructure_unfunded_usd'])) for x in values
        )
        funded_by_provider=self._provider_funding_totals(db)
        costs_by_provider=self._provider_costs(db,commercial_lots)
        released_credit_by_provider=self._provider_credit_release_totals(db)
        providers=sorted(
            set(funded_by_provider)
            | set(costs_by_provider)
            | set(released_credit_by_provider)
        )
        pending_recovery = pending_recovery_service.list_pending(db)['summary']

        provider_balances=[]
        for provider in providers:
            funded=funded_by_provider.get(provider,D('0'))
            cost=costs_by_provider.get(provider,D('0'))
            provider_balances.append({
                'provider':provider,
                'funded_usd':float(funded),
                'infrastructure_cost_usd':float(cost),
                'credit_available_usd':float(max(funded-cost,D('0'))),
                'unfunded_cost_usd':float(max(cost-funded,D('0'))),
                'released_credit_usd':float(released_credit_by_provider.get(provider,D('0'))),
            })

        return {
            'collected_usd':float(sum(D(str(x['amount_paid_usd'])) for x in values)),
            'available_usd':float(available),
            'protected_infrastructure_usd':float(protected),
            'blocked_profit_usd':float(blocked),
            'released_commercial_profit_usd':float(released),
            'rounding_and_operational_surplus_usd':float(rounding),
            'expiration_releases_usd':float(expir),
            'withdrawals_usd':float(withdrawals),
            'infrastructure_cash_available_usd':float(infrastructure_cash_available),
            'infrastructure_funded_usd':float(sum(funded_by_provider.values())),
            'provider_credit_available_usd':float(sum(max(
                funded_by_provider.get(provider,D('0'))-costs_by_provider.get(provider,D('0')),
                D('0'),
            ) for provider in providers)),
            'provider_cost_unfunded_usd':float(sum(max(
                costs_by_provider.get(provider,D('0'))-funded_by_provider.get(provider,D('0')),
                D('0'),
            ) for provider in providers)),
            'provider_credit_released_usd':float(sum(released_credit_by_provider.values())),
            'provider_balances':provider_balances,
            'pending_recovery_generations':int(pending_recovery['pending_generations']),
            'pending_recovery_tokens':int(pending_recovery['pending_tokens']),
            'pending_recovery_infrastructure_usd':float(pending_recovery['infrastructure_pending_usd']),
            'pending_recovery_profit_estimated_usd':float(pending_recovery['profit_pending_estimated_usd']),
            'pending_recovery_economic_estimated_usd':float(pending_recovery['economic_pending_estimated_usd']),
            'active_bags':sum(x['status']=='active' for x in values),
            'new_bags':sum(x['status']=='new' for x in values),
            'expired_bags':sum(x['status']=='expired' for x in values),
        }

    def withdrawals(self,db): return db.execute(select(FinanceWithdrawal).order_by(FinanceWithdrawal.withdrawn_at.desc())).scalars().all()
    def create_withdrawal(self,db,data,admin_id):
        available=D(str(self.summary(db)['available_usd'])); amount=D(str(data.amount_usd))
        if amount>available: raise ConflictException(f'Withdrawal exceeds available cash. Available: USD {available}.')
        row=FinanceWithdrawal(amount_usd=amount,currency='USD',beneficiary=data.beneficiary,concept=data.concept,method=data.method,proof_url=data.proof_url,notes=data.notes,created_by_user_id=admin_id,withdrawn_at=data.withdrawn_at or utc_now()); db.add(row); db.flush(); return row
finance_cashbox_service=FinanceCashboxService()
