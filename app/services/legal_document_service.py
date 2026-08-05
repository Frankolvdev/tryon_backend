import hashlib, json
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.common.exceptions import ConflictException, NotFoundException
from app.common.time import utc_now
from app.models.legal_document import LegalDocument
from app.models.legal_acceptance import LegalAcceptance

REQUIRED_TYPES=("terms","privacy","refund","credit_expiration","immediate_service","first_token_activation")
DEFAULTS={
"terms":("Términos y Condiciones","Al comprar créditos aceptas usarlos exclusivamente dentro de la plataforma, respetar las reglas del servicio y proporcionar información verdadera."),
"privacy":("Política de Privacidad","Tratamos los datos necesarios para operar la cuenta, procesar pagos, prestar el servicio y conservar evidencia de las decisiones del usuario."),
"refund":("Política de Reembolsos","Las bolsas sin consumo pueden ser elegibles para reembolso. Tras el primer consumo, la bolsa deja de ser elegible salvo que la legislación aplicable exija lo contrario."),
"credit_expiration":("Política de Caducidad de Créditos","Los créditos vencen en la fecha informada antes de comprar y visible en la cuenta. Los créditos expirados dejan de estar disponibles."),
"immediate_service":("Inicio inmediato del servicio digital","Solicito que el servicio digital comience inmediatamente después de la compra."),
"first_token_activation":("Activación con el primer consumo","Entiendo que consumir el primer token activa la bolsa y puede afectar su elegibilidad para reembolso conforme a la ley aplicable."),
}
class LegalDocumentService:
 def _hash(self,content): return hashlib.sha256(content.encode()).hexdigest()
 def seed_defaults(self,db):
  for typ,(title,content) in DEFAULTS.items():
   exists=db.execute(select(LegalDocument).where(LegalDocument.document_type==typ)).scalar_one_or_none()
   if not exists: db.add(LegalDocument(document_type=typ,title=title,content=content,version="1.0",language="es",country_scope="*",is_required=True,is_published=True,effective_at=utc_now(),published_at=utc_now(),content_hash=self._hash(content)))
  db.commit()
 def list(self,db,published_only=False,language=None):
  self.seed_defaults(db); q=select(LegalDocument)
  if published_only:q=q.where(LegalDocument.is_published.is_(True))
  if language:q=q.where(LegalDocument.language==language)
  return list(db.execute(q.order_by(LegalDocument.document_type,LegalDocument.created_at.desc())).scalars())
 def create(self,db,data,user_id=None):
  d=LegalDocument(**data.model_dump(),is_published=False,content_hash=self._hash(data.content),created_by_user_id=user_id);db.add(d);db.commit();db.refresh(d);return d
 def update(self,db,doc_id,data):
  d=db.get(LegalDocument,doc_id)
  if not d:raise NotFoundException("Legal document not found.")
  if d.is_published:raise ConflictException("Published legal versions are immutable. Create a new version.")
  for k,v in data.model_dump().items():setattr(d,k,v)
  d.content_hash=self._hash(d.content);db.commit();db.refresh(d);return d
 def publish(self,db,doc_id,user_id=None):
  d=db.get(LegalDocument,doc_id)
  if not d:raise NotFoundException("Legal document not found.")
  db.query(LegalDocument).filter(LegalDocument.document_type==d.document_type,LegalDocument.language==d.language,LegalDocument.id!=d.id).update({"is_published":False})
  d.is_published=True;d.published_at=utc_now();d.effective_at=d.effective_at or utc_now();d.published_by_user_id=user_id;db.commit();db.refresh(d);return d
 def active(self,db,language="es",country=None):
  docs=self.list(db,True,language)
  latest={}
  for d in docs:
   scopes=[x.strip().upper() for x in d.country_scope.split(',')]
   if '*' in scopes or not country or country.upper() in scopes:latest.setdefault(d.document_type,d)
  return list(latest.values())
 def validate_bundle(self,db,bundle,language="es",country=None):
  if not bundle or not bundle.immediate_service_start or not bundle.first_token_activation_acknowledged:raise ConflictException("You must accept the legal policies and immediate digital service conditions.")
  active={d.document_type:d for d in self.active(db,language,country)}; supplied={x.document_id:x for x in bundle.acceptances}
  missing=[]; resolved=[]
  for typ in REQUIRED_TYPES:
   d=active.get(typ)
   if not d: missing.append(typ);continue
   item=supplied.get(d.id)
   if not item or item.version!=d.version:missing.append(typ)
   else:resolved.append(d)
  if missing:raise ConflictException("Missing or outdated legal acceptances: "+", ".join(missing))
  return resolved
 def record(self,db,*,user_id,documents,context,reference,purchase_id=None,payment_id=None,bag_id=None,ip=None,country=None,language=None,user_agent=None):
  for d in documents:
   exists=db.execute(select(LegalAcceptance).where(LegalAcceptance.user_id==user_id,LegalAcceptance.legal_document_id==d.id,LegalAcceptance.context==context,LegalAcceptance.context_reference==reference)).scalar_one_or_none()
   if not exists:db.add(LegalAcceptance(user_id=user_id,legal_document_id=d.id,document_type=d.document_type,document_version=d.version,document_hash=d.content_hash,context=context,context_reference=reference,token_purchase_id=purchase_id,billing_payment_id=payment_id,token_bag_id=bag_id,ip_address=ip,country_code=country,language=language,user_agent=user_agent))
  db.commit()
legal_document_service=LegalDocumentService()
