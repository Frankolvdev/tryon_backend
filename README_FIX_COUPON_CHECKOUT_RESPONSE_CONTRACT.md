# FIX Backend - Coupon checkout response contract

Corrige el error:

`AttributeError: 'BillingCouponValidationResponse' object has no attribute 'final_amount'`

El servicio de cupones ya calculaba el descuento y el importe final, pero el esquema Pydantic no declaraba esos campos. Pydantic los descartaba y el checkout fallaba al intentar leerlos.

Campos preservados ahora:

- discount_amount
- final_amount
- requested_discount_percent
- effective_discount_percent
- protected_discount_percent
- potential_loss_usd

No requiere migración Alembic.

Prueba:

`python -m pytest tests/test_billing_coupon_validation_response_contract.py -v`
