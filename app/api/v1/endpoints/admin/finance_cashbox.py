from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session
from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.models.user import User
from app.schemas.finance_cashbox import *
from app.services.audit_service import audit_service
from app.services.finance_cashbox_service import finance_cashbox_service
router=APIRouter(prefix='/finances')
@router.get('/cashbox',response_model=CashboxSummaryResponse)
def cashbox(db:Session=Depends(get_db),current_admin:User=Depends(admin_guard)):
 result=finance_cashbox_service.summary(db); db.commit(); return result
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
@router.get('/token-bag-expiration',response_model=ExpirationSettingsResponse)
def expiry(db:Session=Depends(get_db),current_admin:User=Depends(admin_guard)): return finance_cashbox_service.expiration_settings(db)
@router.put('/token-bag-expiration',response_model=ExpirationSettingsResponse)
def update_expiry(data:ExpirationSettingsUpdate,db:Session=Depends(get_db),current_admin:User=Depends(admin_guard)): result=finance_cashbox_service.set_expiration_settings(db,enabled=data.enabled,days=data.days); db.commit(); return result
