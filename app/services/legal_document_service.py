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
"terms":("Términos y Condiciones","""1. Objeto y aceptación. Estos Términos regulan el acceso y uso de la plataforma, sus herramientas de inteligencia artificial, planes, paquetes y créditos de servicio. Al crear una cuenta, adquirir créditos o utilizar una función, el usuario confirma que leyó, comprendió y aceptó la versión vigente mostrada antes de la compra.

2. Cuenta y seguridad. El usuario debe proporcionar información verdadera, proteger sus credenciales y avisar de cualquier uso no autorizado. La cuenta es personal salvo que el plan contratado permita expresamente usuarios adicionales.

3. Créditos de servicio. Los tokens o créditos son unidades internas que permiten solicitar generaciones y otras operaciones digitales. No son dinero electrónico, no generan intereses, no pueden transferirse fuera de la plataforma y su valor, vigencia, descuento y condiciones quedan registrados en la bolsa creada con cada compra.

4. Servicio de inteligencia artificial. Los resultados pueden variar según los datos de entrada, modelos y proveedores. La plataforma no garantiza que todo resultado sea exacto, único o adecuado para una finalidad específica. El usuario es responsable de revisar el resultado y de contar con derechos sobre el material que carga.

5. Usos prohibidos. No se permite utilizar el servicio para contenido ilegal, fraude, suplantación, explotación, daño a terceros, vulneración de privacidad o derechos de autor, ni para eludir medidas técnicas o de seguridad.

6. Precios y pagos. El precio final, moneda, descuento, cantidad de créditos y vigencia se muestran antes de confirmar. Los pagos son procesados por proveedores externos. Los impuestos, cuando correspondan, se calcularán según la información disponible y la legislación aplicable.

7. Reembolsos, activación y caducidad. Las compras se rigen por las políticas de Reembolsos, Caducidad e Inicio Inmediato aceptadas en el checkout. El primer consumo de una bolsa puede cambiar su elegibilidad para devolución, sin limitar derechos obligatorios que la ley conceda al consumidor.

8. Disponibilidad y cambios. Podemos realizar mantenimiento, corregir errores, actualizar modelos o modificar funciones. Los cambios relevantes a estos Términos se publicarán como una nueva versión y no alterarán silenciosamente la versión aceptada en una compra anterior.

9. Responsabilidad. En la medida permitida por la ley, la plataforma no responde por pérdidas indirectas, decisiones tomadas únicamente con base en resultados de IA o incumplimientos causados por información o material proporcionado por el usuario.

10. Contacto y ley aplicable. Las consultas deben enviarse por los canales oficiales publicados. Cualquier cláusula se interpretará respetando los derechos irrenunciables del consumidor en su jurisdicción. Este texto es un modelo administrativo y debe revisarse jurídicamente antes del lanzamiento comercial."""),
"privacy":("Política de Privacidad","""1. Alcance. Esta Política explica cómo se tratan los datos necesarios para crear cuentas, procesar pagos, prestar funciones de inteligencia artificial, proteger la plataforma y conservar evidencia de operaciones y consentimientos.

2. Datos tratados. Podemos tratar datos de cuenta y contacto, información técnica como IP, dispositivo y registros de acceso, datos de compra y facturación, archivos cargados, resultados generados, comunicaciones de soporte y las versiones de políticas aceptadas. No almacenamos directamente los datos completos de la tarjeta cuando el pago es procesado por Stripe u otro proveedor autorizado.

3. Finalidades. Los datos se utilizan para autenticar al usuario, ejecutar solicitudes, entregar resultados, prevenir fraude y abuso, atender soporte, conciliar pagos, administrar bolsas de créditos, cumplir obligaciones legales y mejorar la estabilidad del servicio.

4. Archivos y resultados. Los archivos pueden almacenarse en infraestructura local o proveedores de almacenamiento configurados. Se conservarán durante el plazo necesario para prestar el servicio, cumplir la configuración de la cuenta o atender obligaciones legales. El usuario puede solicitar su eliminación cuando resulte aplicable.

5. Proveedores. Podemos utilizar proveedores de pagos, nube, GPU, almacenamiento, correo, analítica y seguridad. Solo se comparte la información necesaria para su función y bajo los contratos o garantías correspondientes.

6. Conservación. Los datos financieros, consentimientos, auditorías y evidencias pueden conservarse durante los plazos exigidos por ley. Los archivos operativos y resultados se conservarán conforme a la configuración y políticas publicadas.

7. Derechos. Según la jurisdicción, el usuario puede solicitar acceso, corrección, eliminación, oposición, limitación o portabilidad. Algunas solicitudes pueden estar limitadas por obligaciones fiscales, antifraude, de defensa jurídica o de conservación.

8. Seguridad. Aplicamos controles razonables de acceso, registro, cifrado y segregación. Ningún sistema es absolutamente infalible; por ello también se requiere que el usuario proteja sus credenciales.

9. Transferencias internacionales. Los proveedores pueden operar en otros países. Cuando sea necesario se utilizarán mecanismos legales adecuados para proteger los datos.

10. Contacto y cambios. Las consultas de privacidad se reciben por los canales oficiales. Las nuevas versiones se publicarán con fecha y alcance. Este texto es un modelo administrativo y debe revisarse jurídicamente antes del lanzamiento comercial."""),
"refund":("Política de Reembolsos","""1. Principio general. Una bolsa de créditos pagada y que no haya consumido ningún token puede solicitarse para revisión de reembolso, siempre que el pago sea verificable, no exista disputa o contracargo y la legislación aplicable no establezca una regla distinta.

2. Inicio del consumo. Cuando una bolsa aporta su primer token a una generación u otra operación, el servicio digital se considera iniciado respecto de esa bolsa. Desde ese momento, la bolsa deja de ser elegible para reembolso automático, salvo error atribuible a la plataforma, obligación legal, fraude comprobado u otra excepción aprobada.

3. Fallos técnicos. Si una operación falla, se cancela o no entrega el servicio, los tokens y cargos se ajustarán conforme a la política por resultado configurada. La devolución de tokens no equivale necesariamente a un reembolso monetario.

4. Pagos duplicados o incorrectos. Los pagos duplicados, importes cobrados por error o compras no autorizadas serán investigados. Podemos solicitar evidencia adicional antes de resolver.

5. Suscripciones. La cancelación evita renovaciones futuras, pero no implica por sí sola la devolución de periodos ya iniciados o créditos ya utilizados. Los derechos obligatorios del consumidor prevalecen.

6. Procedimiento. Los reembolsos se tramitan desde el registro de la bolsa correspondiente para actualizar de manera coordinada el pago, los créditos, la reserva de infraestructura y la caja financiera.

7. Método y plazo. Los reembolsos aprobados se enviarán, cuando sea posible, al método de pago original. El tiempo de reflejo depende de Stripe, el banco y la red de pago.

8. Disputas. Si existe una disputa o contracargo, la bolsa y los movimientos relacionados pueden bloquearse hasta su resolución.

9. Excepciones legales. Nada en esta política elimina garantías o derechos irrenunciables previstos en la jurisdicción del consumidor. Este texto es un modelo administrativo y debe revisarse jurídicamente antes del lanzamiento comercial."""),
"credit_expiration":("Política de Caducidad de Créditos","""1. Vigencia informada. Cada bolsa de créditos registra una fecha de compra y una fecha de vencimiento calculada con la configuración vigente al momento de adquirirla. La vigencia se muestra antes de pagar y permanece visible en la cuenta.

2. Efecto del vencimiento. Al alcanzar la fecha indicada, los créditos restantes se marcan como expirados y dejan de estar disponibles para nuevas operaciones. No se registran como generaciones ficticias ni como tokens consumidos.

3. Condiciones congeladas. Cambiar posteriormente la vigencia global no modifica de manera retroactiva la fecha de bolsas ya creadas, salvo que la plataforma conceda una extensión favorable al usuario o la ley lo exija.

4. Avisos. Cuando la función esté habilitada, podrán enviarse avisos antes del vencimiento. La ausencia o fallo de un aviso no modifica por sí mismo la fecha claramente mostrada en la compra y en la cuenta, salvo disposición legal.

5. Saldo económico. Al expirar una bolsa, termina la obligación de prestar futuras operaciones con esos créditos y el sistema registra la liberación financiera correspondiente de manera separada y auditable.

6. Reembolsos y excepciones. La caducidad no crea automáticamente un derecho de reembolso. Se respetarán las excepciones y plazos obligatorios de la legislación aplicable.

7. Recomendación. El usuario debe revisar regularmente sus bolsas y utilizar los créditos antes de su vencimiento. Este texto es un modelo administrativo y debe revisarse jurídicamente antes del lanzamiento comercial."""),
"immediate_service":("Inicio inmediato del servicio digital","""Solicito expresamente que el servicio digital quede disponible inmediatamente después de confirmarse el pago, sin esperar a que termine un eventual plazo general de desistimiento. Comprendo que podré utilizar los créditos para solicitar operaciones de inteligencia artificial desde ese momento y que el inicio efectivo del consumo puede modificar o extinguir el derecho de desistimiento en los casos permitidos por la legislación aplicable. Esta aceptación no limita garantías obligatorias por servicios defectuosos, cobros indebidos ni otros derechos irrenunciables."""),
"first_token_activation":("Activación con el primer consumo","""Comprendo que cada compra crea una bolsa independiente con su propio precio, descuento, ganancia, reserva de infraestructura, vigencia y políticas aceptadas. La bolsa permanece sin uso hasta que aporte su primer token a una generación u operación. Al producirse ese primer consumo, el servicio digital asociado a esa bolsa se considera iniciado, la bolsa pasa a estado activa y deja de ser elegible para reembolso automático, salvo las excepciones previstas en la Política de Reembolsos o exigidas por la legislación aplicable."""),
}
LEGACY_DEFAULT_CONTENT={
"terms":"Al comprar créditos aceptas usarlos exclusivamente dentro de la plataforma, respetar las reglas del servicio y proporcionar información verdadera.",
"privacy":"Tratamos los datos necesarios para operar la cuenta, procesar pagos, prestar el servicio y conservar evidencia de las decisiones del usuario.",
"refund":"Las bolsas sin consumo pueden ser elegibles para reembolso. Tras el primer consumo, la bolsa deja de ser elegible salvo que la legislación aplicable exija lo contrario.",
"credit_expiration":"Los créditos vencen en la fecha informada antes de comprar y visible en la cuenta. Los créditos expirados dejan de estar disponibles.",
"immediate_service":"Solicito que el servicio digital comience inmediatamente después de la compra.",
"first_token_activation":"Entiendo que consumir el primer token activa la bolsa y puede afectar su elegibilidad para reembolso conforme a la ley aplicable.",
}
PROFESSIONAL_DEFAULT_VERSION="1.1"
class LegalDocumentService:
 def _hash(self,content): return hashlib.sha256(content.encode()).hexdigest()
 def seed_defaults(self,db):
  for typ,(title,content) in DEFAULTS.items():
   docs=list(db.execute(select(LegalDocument).where(LegalDocument.document_type==typ,LegalDocument.language=="es").order_by(LegalDocument.created_at.desc())).scalars())
   if not docs:
    db.add(LegalDocument(document_type=typ,title=title,content=content,version=PROFESSIONAL_DEFAULT_VERSION,language="es",country_scope="*",is_required=True,is_published=True,effective_at=utc_now(),published_at=utc_now(),content_hash=self._hash(content)))
    continue
   legacy=next((d for d in docs if d.content.strip()==LEGACY_DEFAULT_CONTENT.get(typ,"")),None)
   professional=next((d for d in docs if d.content_hash==self._hash(content)),None)
   # Upgrade only the exact short seed shipped by the platform. Never replace administrator-authored text.
   if legacy and not professional:
    for d in docs:d.is_published=False
    db.add(LegalDocument(document_type=typ,title=title,content=content,version=PROFESSIONAL_DEFAULT_VERSION,language="es",country_scope="*",is_required=True,is_published=True,effective_at=utc_now(),published_at=utc_now(),content_hash=self._hash(content)))
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
