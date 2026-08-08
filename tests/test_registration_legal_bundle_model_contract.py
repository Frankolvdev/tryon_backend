from pathlib import Path


def test_registration_keeps_legal_bundle_as_validated_model():
    source = Path('app/services/user_service.py').read_text(encoding='utf-8')
    assert 'legal_bundle = user_data.legal' in source
    assert 'user_dict.pop("legal", None)' in source
    assert 'legal_bundle = user_dict.pop("legal", None)' not in source
