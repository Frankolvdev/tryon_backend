# Fix: Generation readiness pricing-rule relation

Corrige el error:

`AttributeError: 'GenerationModule' object has no attribute 'pricing_rule_id'`

La relación real está en `PricingRule.generation_module_id`, por lo que el gate ahora usa:

```python
pricing_rule_repository.get_for_generation_module(db, module.id)
```

No modifica pipeline, cancelaciones, Modal, Beam, RunPod, snapshots, Redis ni Runtime Builder.
