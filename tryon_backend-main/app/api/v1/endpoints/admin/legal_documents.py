from fastapi import APIRouter,Depends
from sqlalchemy.orm import Session
from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.models.user import User
from app.schemas.legal import LegalDocumentWrite,LegalDocumentResponse
from app.services.legal_document_service import legal_document_service
router=APIRouter(prefix="/legal-documents")
@router.get("",response_model=list[LegalDocumentResponse])
def listing(db:Session=Depends(get_db),_:User=Depends(admin_guard)):return legal_document_service.list(db)
@router.post("",response_model=LegalDocumentResponse)
def create(data:LegalDocumentWrite,db:Session=Depends(get_db),u:User=Depends(admin_guard)):return legal_document_service.create(db,data,u.id)
@router.put("/{doc_id}",response_model=LegalDocumentResponse)
def update(doc_id:int,data:LegalDocumentWrite,db:Session=Depends(get_db),_:User=Depends(admin_guard)):return legal_document_service.update(db,doc_id,data)
@router.post("/{doc_id}/publish",response_model=LegalDocumentResponse)
def publish(doc_id:int,db:Session=Depends(get_db),u:User=Depends(admin_guard)):return legal_document_service.publish(db,doc_id,u.id)
