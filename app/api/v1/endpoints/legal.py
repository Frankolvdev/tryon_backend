from fastapi import APIRouter,Depends,Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.v1.deps import get_db
from app.api.v1.guards.auth_guard import auth_guard
from app.models.user import User
from app.models.token_value_lot import TokenValueLot
from app.models.legal_acceptance import LegalAcceptance
from app.schemas.legal import LegalDocumentResponse,TokenBagPublicResponse
from app.services.legal_document_service import legal_document_service
router=APIRouter()
@router.get("/policies",response_model=list[LegalDocumentResponse])
def policies(language:str="es",country:str|None=None,db:Session=Depends(get_db)):
 return legal_document_service.active(db,language,country)
@router.get("/my-token-bags",response_model=list[TokenBagPublicResponse])
def bags(db:Session=Depends(get_db),user:User=Depends(auth_guard)):
 lots=db.execute(select(TokenValueLot).where(TokenValueLot.user_id==user.id).order_by(TokenValueLot.created_at.desc())).scalars().all();out=[]
 for lot in lots:
  accepts=db.execute(select(LegalAcceptance).where(LegalAcceptance.token_bag_id==lot.id)).scalars().all()
  consumed=max(0,lot.original_tokens-lot.remaining_tokens)
  out.append(TokenBagPublicResponse(id=lot.id,source=lot.source,original_tokens=lot.original_tokens,remaining_tokens=lot.remaining_tokens,status=lot.status,created_at=lot.created_at,expires_at=lot.expires_at,refundable=lot.status=='new' and consumed==0 and not lot.refunded_at,accepted_documents=[{"type":a.document_type,"version":a.document_version,"accepted_at":a.accepted_at.isoformat()} for a in accepts]))
 return out
