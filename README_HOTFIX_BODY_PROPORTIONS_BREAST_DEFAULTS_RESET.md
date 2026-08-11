# Hotfix Backend — Breast defaults + reset control

Cambios:
- Big Breast default real: 0.9
- Huge Breast default real: 1.8
- Elimina los boosts internos de preview (+0.2 / +0.5)
- breasts_max default: 1.8
- Migra únicamente defaults legacy Big 1.0 -> 0.9, Huge 1.5 -> 1.8 y breasts_max 1.5 -> 1.8
- Reset acepta `delete_workflow_mappings=true|false`
- Si es false, conserva workflow + mappings y reinicia reglas/datos de esta tool
- Si es true, elimina también la configuración de workflow/mappings

No modifica módulos ajenos.
