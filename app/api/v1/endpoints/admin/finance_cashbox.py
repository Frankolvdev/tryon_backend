from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session
from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.models.user import User
from app.repositories.user_repository import user_repository
from app.common.exceptions import ConflictException
from app.schemas.finance_cashbox import *
from app.schemas.promotional_credit import *
from app.services.audit_service import audit_service
from app.services.finance_cashbox_service import finance_cashbox_service
from app.services.pending_recovery_service import pending_recovery_service
from app.services.promotional_credit_service import promotional_credit_service
from app.services.promotional_funding_cycle_service import promotional_funding_cycle_service
router=APIRouter(prefix='/finances')
@router.get('/cashbox',response_model=CashboxSummaryResponse)
def cashbox(db:Session=Depends(get_db),current_admin:User=Depends(admin_guard)):
 result=finance_cashbox_service.summary(db); db.commit(); return result

@router.get('/pending-recoveries',response_model=PendingRecoveryListResponse)
def pending_recoveries(db:Session=Depends(get_db),current_admin:User=Depends(admin_guard)):
 return pending_recovery_service.list_pending(db)

@router.get('/token-bags',response_model=TokenBagListResponse)
def bags(status:str|None=Query(None),user_id:int|None=Query(None),skip:int=0,limit:int=Query(100,le=200),db:Session=Depends(get_db),current_admin:User=Depends(admin_guard)):
 result=finance_cashbox_service.list_bags(db,status=status,user_id=user_id,skip=skip,limit=limit); db.commit(); return result
@router.get('/token-bags/{bag_id}',response_model=TokenBagDetailResponse)
def bag_detail(bag_id:int,db:Session=Depends(get_db),current_admin:User=Depends(admin_guard)):
 result=finance_cashbox_service.detail(db,bag_id); db.commit(); return result
@router.get('/withdrawals',response_model=list[WithdrawalResponse])
def withdrawals(db:Session=Depends(get_db),current_admin:User=Depends(admin_guard)): return finance_cashbox_service.withdrawals(db)
@router.post('/withdrawals',response_model=WithdrawalResponse)
def create_withdrawal(data:WithdrawalCreate,request:Request,db:Session=Depends(get_db),current_admin:User=Depends(admin_guard)):
 row=finance_cashbox_service.create_withdrawal(db,data,current_admin.id); audit_service.create_log(db,actor_user_id=current_admin.id,action='finance_withdrawal_created',entity_type='finance_withdrawal',entity_id=str(row.id),description=f'Withdrawal of USD {row.amount_usd} registered.',ip_address=request.client.host if request.client else None,user_agent=request.headers.get('user-agent')); db.commit(); db.refresh(row); return row
@router.get('/infrastructure-fundings',response_model=list[InfrastructureFundingResponse])
def infrastructure_fundings(db:Session=Depends(get_db),current_admin:User=Depends(admin_guard)):
 return finance_cashbox_service.infrastructure_fundings(db)

@router.post('/infrastructure-fundings',response_model=InfrastructureFundingResponse)
def create_infrastructure_funding(data:InfrastructureFundingCreate,request:Request,db:Session=Depends(get_db),current_admin:User=Depends(admin_guard)):
 result=finance_cashbox_service.create_infrastructure_funding(db,data,current_admin.id)
 audit_service.create_log(db,actor_user_id=current_admin.id,action='infrastructure_funding_created',entity_type='infrastructure_funding_movement',entity_id=str(result['id']),description=f"Infrastructure funding of USD {result['amount_usd']} registered for {result['provider']}.",ip_address=request.client.host if request.client else None,user_agent=request.headers.get('user-agent'))
 db.commit()
 return result

@router.get('/token-bag-expiration',response_model=ExpirationSettingsResponse)
def expiry(db:Session=Depends(get_db),current_admin:User=Depends(admin_guard)): return finance_cashbox_service.expiration_settings(db)
@router.put('/token-bag-expiration',response_model=ExpirationSettingsResponse)
def update_expiry(data:ExpirationSettingsUpdate,db:Session=Depends(get_db),current_admin:User=Depends(admin_guard)): result=finance_cashbox_service.set_expiration_settings(db,enabled=data.enabled,days=data.days); db.commit(); return result
@router.post('/token-bags/{bag_id}/simulate-expiration',response_model=TokenBagExpirationSimulationResponse)
def simulate_expiration(bag_id:int,data:TokenBagExpirationSimulationRequest,request:Request,db:Session=Depends(get_db),current_admin:User=Depends(admin_guard)):
 if not data.confirm: raise ConflictException('Explicit confirmation is required to simulate expiration.')
 result=finance_cashbox_service.simulate_expiration(db,bag_id)
 audit_service.create_log(db,actor_user_id=current_admin.id,action='token_bag_expiration_simulated',entity_type='token_value_lot',entity_id=str(bag_id),description=(f"Expiration simulated for token bag #{bag_id}: USD {result.get('promotional_credit_returned_usd',0)} returned to promotional credit, USD {result['infrastructure_cash_released_usd']} moved to withdrawable cash and USD {result['provider_credit_released_usd']} remained as provider credit."),ip_address=request.client.host if request.client else None,user_agent=request.headers.get('user-agent'))
 db.commit(); return result


@router.get('/promotional-credits',response_model=PromotionalCreditSummary)
def promotional_credits(db:Session=Depends(get_db),current_admin:User=Depends(admin_guard)):
 result=promotional_credit_service.summary(db); db.commit(); return result

@router.post('/promotional-credits/funds',response_model=PromotionalFundResponse)
def create_promotional_fund(data:PromotionalFundCreate,request:Request,db:Session=Depends(get_db),current_admin:User=Depends(admin_guard)):
 row=promotional_credit_service.add_fund(db,amount_usd=data.amount_usd,provider=data.provider,reference=data.reference,description=data.description,created_by_user_id=current_admin.id)
 audit_service.create_log(db,actor_user_id=current_admin.id,action='promotional_credit_fund_added',entity_type='promotional_credit_fund',entity_id=str(row.id),description=f'Promotional provider credit of USD {row.original_usd} added for {row.provider}.',ip_address=request.client.host if request.client else None,user_agent=request.headers.get('user-agent'))
 db.commit(); db.refresh(row); return row

@router.post('/promotional-credits/recurring-sources',response_model=PromotionalRecurringSourceResponse)
def create_promotional_recurring_source(data:PromotionalRecurringSourceCreate,request:Request,db:Session=Depends(get_db),current_admin:User=Depends(admin_guard)):
 provider=promotional_credit_service.normalize_provider(data.provider)
 source=promotional_funding_cycle_service.create_source(
  db,name=data.name,provider=provider,recurring_amount_usd=data.recurring_amount_usd,
  current_available_usd=data.current_available_usd,cycle_start=data.cycle_start,recurrence=data.recurrence,
  simulation_enabled=data.simulation_enabled,created_by_user_id=current_admin.id,
 )
 audit_service.create_log(db,actor_user_id=current_admin.id,action='promotional_recurring_source_created',entity_type='promotional_funding_source',entity_id=str(source.id),description=f'Recurring promotional source {source.name} created for {provider}: current available USD {data.current_available_usd}; next full cycles USD {data.recurring_amount_usd}.',ip_address=request.client.host if request.client else None,user_agent=request.headers.get('user-agent'))
 result=next(item for item in promotional_funding_cycle_service.summary(db) if item['id']==source.id)
 db.commit(); return result

@router.put('/promotional-credits/recurring-sources/{source_id}',response_model=PromotionalRecurringSourceResponse)
def update_promotional_recurring_source(source_id:int,data:PromotionalRecurringSourceUpdate,request:Request,db:Session=Depends(get_db),current_admin:User=Depends(admin_guard)):
 source=promotional_funding_cycle_service.update_source(db,source_id=source_id,name=data.name,recurring_amount_usd=data.recurring_amount_usd,recurrence=data.recurrence,simulation_enabled=data.simulation_enabled,active=data.active)
 audit_service.create_log(db,actor_user_id=current_admin.id,action='promotional_recurring_source_updated',entity_type='promotional_funding_source',entity_id=str(source.id),description=f'Recurring promotional source {source.name} updated. New cycles use USD {source.recurring_amount_usd}. Active={source.active}.',ip_address=request.client.host if request.client else None,user_agent=request.headers.get('user-agent'))
 result=next(item for item in promotional_funding_cycle_service.summary(db) if item['id']==source.id)
 db.commit(); return result

@router.post('/promotional-credits/recurring-sources/{source_id}/cycle-webhook',response_model=PromotionalCycleWebhookResult)
def promotional_cycle_webhook(source_id:int,data:PromotionalCycleWebhookRequest,request:Request,db:Session=Depends(get_db),current_admin:User=Depends(admin_guard)):
 result=promotional_funding_cycle_service.trigger_webhook(db,source_id=source_id,simulation=data.simulation,simulation_date=data.simulation_date)
 audit_service.create_log(
  db,
  actor_user_id=current_admin.id,
  action='promotional_cycle_webhook_simulated' if data.simulation else 'promotional_cycle_webhook_triggered',
  entity_type='promotional_funding_source',
  entity_id=str(source_id),
  description=result['message'],
  ip_address=request.client.host if request.client else None,
  user_agent=request.headers.get('user-agent'),
 )
 db.commit()
 return result

@router.put('/promotional-credits/settings',response_model=PromotionalCreditSettings)
def update_promotional_settings(data:PromotionalCreditSettings,request:Request,db:Session=Depends(get_db),current_admin:User=Depends(admin_guard)):
 result=promotional_credit_service.update_settings(db,signup_enabled=data.signup_enabled,signup_tokens=data.signup_tokens,signup_provider=data.signup_provider,allow_pending_settlement=data.allow_pending_settlement)
 audit_service.create_log(db,actor_user_id=current_admin.id,action='promotional_credit_settings_updated',entity_type='system_setting',entity_id='promotional_credits',description='Promotional credit settings updated.',ip_address=request.client.host if request.client else None,user_agent=request.headers.get('user-agent'))
 db.commit(); return result

@router.post('/promotional-credits/grants',response_model=PromotionalGrantResult)
def create_promotional_grant(data:PromotionalGrantCreate,request:Request,db:Session=Depends(get_db),current_admin:User=Depends(admin_guard)):
 user=None
 if data.user_id is not None:
  user=user_repository.get_by_id(db,data.user_id)
 elif data.user_email:
  user=user_repository.get_by_email(db,str(data.user_email).strip().lower())
 if not user: raise ConflictException('User not found.')
 result=promotional_credit_service.grant(db,user_id=user.id,tokens=data.tokens,provider=data.provider,grant_type='manual_admin',created_by_user_id=current_admin.id,allow_partial=False)
 audit_service.create_log(db,actor_user_id=current_admin.id,action='promotional_tokens_granted',entity_type='user',entity_id=str(user.id),description=f"{result['granted_tokens']} promotional token(s) granted from {result['provider']} credit.",ip_address=request.client.host if request.client else None,user_agent=request.headers.get('user-agent'))
 db.commit(); return result

@router.post('/promotional-credits/revoke',response_model=PromotionalRevokeResult)
def revoke_promotional_tokens(data:PromotionalRevokeCreate,request:Request,db:Session=Depends(get_db),current_admin:User=Depends(admin_guard)):
 result=promotional_credit_service.revoke_unused(db,user_id=data.user_id,tokens=data.tokens,reason=data.reason)
 audit_service.create_log(db,actor_user_id=current_admin.id,action='promotional_tokens_revoked',entity_type='user',entity_id=str(data.user_id),description=f"{result['revoked_tokens']} unused promotional token(s) removed; USD {result['amount_returned_usd']} returned to their original promotional fund(s).",ip_address=request.client.host if request.client else None,user_agent=request.headers.get('user-agent'))
 db.commit(); return result

from app.schemas.finance_cashbox import (
    OperationalCashboxSummaryResponse, OperationalExpenseCreate, OperationalExpenseResponse,
)
from app.services.operational_cashbox_service import operational_cashbox_service




@router.get('/operational-cashbox', response_model=OperationalCashboxSummaryResponse)
def operational_cashbox(db:Session=Depends(get_db),current_admin:User=Depends(admin_guard)):
    finance_cashbox_service.ensure_expirations(db)
    db.flush()
    return operational_cashbox_service.summary(db)


@router.get('/operational-expenses', response_model=list[OperationalExpenseResponse])
def operational_expenses(db:Session=Depends(get_db),current_admin:User=Depends(admin_guard)):
    return operational_cashbox_service.expenses(db)


@router.post('/operational-expenses', response_model=OperationalExpenseResponse)
def create_operational_expense(data:OperationalExpenseCreate,request:Request,db:Session=Depends(get_db),current_admin:User=Depends(admin_guard)):
    result=operational_cashbox_service.create_expense(db,data,current_admin.id)
    audit_service.create_log(db,actor_user_id=current_admin.id,action='operational_expense_created',entity_type='operational_expense',entity_id=str(result.id),description=f"Operational expense of USD {result.amount_usd} registered: {result.concept}.",ip_address=request.client.host if request.client else None,user_agent=request.headers.get('user-agent'))
    db.commit(); db.refresh(result); return result
