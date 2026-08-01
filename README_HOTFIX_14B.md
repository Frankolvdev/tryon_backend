# Hotfix MegaZIP 14B — Import Modal

El instalador original esperaba una secuencia exacta de imports que no coincide
con el backend actual.

Descomprime este ZIP en la raíz del backend, junto a:

```text
APLICAR_MEGAZIP_14B.py
```

Ejecuta:

```powershell
python .\CORREGIR_APLICADOR_14B.py
python .\APLICAR_MEGAZIP_14B.py
python -m compileall app
pytest tests/test_megazip_14b_modal_engine_contract.py
```

El hotfix solo modifica el instalador. No toca Beam, RunPod, cancelaciones ni el
pipeline.
