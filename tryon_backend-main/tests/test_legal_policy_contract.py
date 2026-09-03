from app.schemas.legal import LegalAcceptanceBundle,LegalAcceptanceInput
def test_bundle_contract():
 b=LegalAcceptanceBundle(acceptances=[LegalAcceptanceInput(document_id=1,version="1.0")],immediate_service_start=True,first_token_activation_acknowledged=True)
 assert b.immediate_service_start
