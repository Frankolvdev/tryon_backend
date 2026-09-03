from fastapi import APIRouter,Depends,Query,Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.v1.deps import get_db
from app.api.v1.guards.auth_guard import auth_guard
from app.models.user import User
from app.models.token_value_lot import TokenValueLot
from app.models.legal_acceptance import LegalAcceptance
from app.schemas.legal import LegalDocumentResponse,TokenBagPublicResponse,LegalAcceptanceBundle,LegalAcceptanceStatusResponse
from app.services.legal_document_service import legal_document_service
router=APIRouter()
@router.get("/policies",response_model=list[LegalDocumentResponse])
def policies(language:str="es",country:str|None=None,db:Session=Depends(get_db)):
 return legal_document_service.active(db,language,country)

@router.get("/acceptance-status",response_model=LegalAcceptanceStatusResponse)
def acceptance_status(language:str="es",country:str|None=None,db:Session=Depends(get_db),user:User=Depends(auth_guard)):
 docs=legal_document_service.active(db,language,country)
 accepted=set(db.execute(select(LegalAcceptance.legal_document_id).where(LegalAcceptance.user_id==user.id)).scalars().all())
 required=[d.id for d in docs if d.is_required]
 missing=[i for i in required if i not in accepted]
 return LegalAcceptanceStatusResponse(complete=not missing,missing_document_ids=missing,accepted_document_ids=sorted(accepted))

@router.post("/accept",response_model=LegalAcceptanceStatusResponse)
def accept_policies(data:LegalAcceptanceBundle,request:Request,language:str="es",country:str|None=None,db:Session=Depends(get_db),user:User=Depends(auth_guard)):
 docs=legal_document_service.validate_bundle(db,data,language,country)
 legal_document_service.record(db,user_id=user.id,documents=docs,context="account_acceptance",reference=str(user.id),ip=request.client.host if request.client else None,country=country,language=language,user_agent=request.headers.get("user-agent"))
 return acceptance_status(language,country,db,user)

@router.get("/my-token-bags",response_model=list[TokenBagPublicResponse])
def bags(db:Session=Depends(get_db),user:User=Depends(auth_guard)):
 lots=db.execute(select(TokenValueLot).where(TokenValueLot.user_id==user.id).order_by(TokenValueLot.created_at.desc())).scalars().all();out=[]
 for lot in lots:
  accepts=db.execute(select(LegalAcceptance).where(LegalAcceptance.token_bag_id==lot.id)).scalars().all()
  consumed=max(0,lot.original_tokens-lot.remaining_tokens)
  out.append(TokenBagPublicResponse(id=lot.id,source=lot.source,original_tokens=lot.original_tokens,remaining_tokens=lot.remaining_tokens,status=lot.status,created_at=lot.created_at,expires_at=lot.expires_at,refundable=lot.status=='new' and consumed==0 and not lot.refunded_at,accepted_documents=[{"type":a.document_type,"version":a.document_version,"accepted_at":a.accepted_at.isoformat()} for a in accepts]))
 return out
