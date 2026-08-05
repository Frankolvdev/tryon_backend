# FIX Backend — Package dynamic quote checkout

- Token-package checkout now calculates the current nominal price from the global token value.
- It applies the package's protected discount using the same service used by the public catalog.
- Coupons are then applied to that exact current package price.
- Stripe receives the final backend-approved dynamic amount.
- No Alembic migration is required.
