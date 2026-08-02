# Fix Modal: región y modelos residentes

- Añade region_mode automatic/fixed y region a Modal.
- Propaga la región al modal_app generado.
- Respeta exactamente snapshot_resident_models; solo usa defaults cuando el valor es None.
- Default actual: realDream + qwen_3_8b.
- No modifica Beam ni RunPod.
