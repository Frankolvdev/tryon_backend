from datetime import datetime
from pydantic import BaseModel, Field

class LegalDocumentWrite(BaseModel):
    document_type: str = Field(min_length=2,max_length=80)
    title: str = Field(min_length=2,max_length=255)
    content: str = Field(min_length=20)
    version: str = Field(min_length=1,max_length=40)
    language: str = Field(default="es",min_length=2,max_length=10)
    country_scope: str = Field(default="*",max_length=500)
    is_required: bool = True
    effective_at: datetime | None = None

class LegalDocumentResponse(LegalDocumentWrite):
    id:int; is_published:bool; content_hash:str; published_at:datetime|None; created_at:datetime; updated_at:datetime
    model_config={"from_attributes":True}

class LegalAcceptanceInput(BaseModel):
    document_id:int=Field(gt=0)
    version:str=Field(min_length=1,max_length=40)

class LegalAcceptanceBundle(BaseModel):
    acceptances:list[LegalAcceptanceInput]=Field(min_length=1)
    immediate_service_start:bool
    first_token_activation_acknowledged:bool

class TokenBagPublicResponse(BaseModel):
    id:int; source:str; original_tokens:int; remaining_tokens:int; status:str
    created_at:datetime; expires_at:datetime|None; refundable:bool
    accepted_documents:list[dict]=[]
