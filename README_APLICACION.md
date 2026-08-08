FIX REGISTRO LEGAL

Corrige el 500 al crear cuenta: UserCreate.model_dump() convertía LegalAcceptanceBundle a dict antes de validate_bundle(). Ahora se conserva el modelo Pydantic validado.

No cambia fórmulas, finanzas, tokens, OAuth, pagos ni modelos DB. No requiere Alembic ni .env.

Validación: compileall OK; 2 tests legales PASSED.

Git:
git add .
git commit -m "fix: preserve validated legal bundle during registration"
git push
