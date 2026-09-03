Backend56 - Modal Runtime Engine hardcode validator contract

Base: tryon_backend-main (55).zip
Production change: app/services/runtime_context_generator_service.py only.

Change:
- The generated modal_app.py completeness validator now requires the hardcoded
  `RUNTIME_ENGINE_ENABLED = True` contract instead of the obsolete environment
  variable name `TRYON_MODAL_RUNTIME_ENGINE_ENABLED`.

Preserved:
- Backend55 Engine hardcode remains unchanged.
- Backend54 SAM3 legacy snapshot warmup removal remains unchanged.
- No pipeline/workflow/runtime.py/model/GPU/region/billing changes.
