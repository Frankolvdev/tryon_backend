from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def text(rel): return (ROOT/rel).read_text(encoding='utf-8')

def test_admin_revoke_is_promotional_only_and_returns_original_backing():
    service=text('app/services/promotional_credit_service.py')
    assert 'def revoke_unused' in service
    assert 'TokenValueLot.source == PROMO_SOURCE' in service
    assert 'TokenValueLot.remaining_tokens > 0' in service
    assert 'PromotionalCreditFund.id == grant.fund_id' in service
    assert 'promotional_funding_cycle_service.restore_amount' in service
    assert 'reason="admin_revoke"' in service
    assert 'source="promotional_credit_admin_revoke"' in service
    assert 'amount <= 0' in service

def test_admin_endpoint_exposes_only_positive_promotional_removal():
    schema=text('app/schemas/promotional_credit.py')
    endpoint=text('app/api/v1/endpoints/admin/finance_cashbox.py')
    assert 'class PromotionalRevokeCreate' in schema
    assert 'tokens: int = Field(gt=0' in schema
    assert "'/promotional-credits/revoke'" in endpoint
    assert 'promotional_credit_service.revoke_unused' in endpoint

def test_legal_defaults_cover_promotional_credits_without_overwriting_custom_docs():
    legal=text('app/services/legal_document_service.py')
    assert 'PROFESSIONAL_DEFAULT_VERSION="1.3"' in legal
    assert 'créditos promocionales o gratuitos' in legal.lower()
    assert 'no tienen valor en efectivo' in legal.lower()
    assert 'PREVIOUS_PROFESSIONAL_DEFAULTS' in legal
    assert 'Never replace administrator-authored text' in legal
