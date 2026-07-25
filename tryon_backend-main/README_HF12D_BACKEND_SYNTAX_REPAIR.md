# HF12D — Reparación de sintaxis del backend

Corrige el error:

```text
SyntaxError: invalid syntax
job = ... RuntimeContextJobService._update(...) job = ...
```

HF12 colocó tres instrucciones consecutivas en una sola línea:

```python
job = create(...) update(...) job = public(...)
```

HF12D las separa correctamente:

```python
job = RuntimeContextJobService.create_model_volume(config.id, payload)

RuntimeContextJobService._update(
    job["job_id"],
    status="queued",
    phase="starting",
    progress=1,
    message="Iniciando exportación de modelos…",
)

job = RuntimeContextJobService.public(job["job_id"])
```

Además, este reparador valida la sintaxis **antes** de volver a escribir el archivo.

## Aplicación

Descomprime directamente sobre `tryon_backend`:

```powershell
python apply_hf12d_backend_syntax_repair.py
python -m compileall app
uvicorn app.main:app --reload --port 8001
```

No vuelvas a ejecutar `apply_hf12_model_export_job_start.py`, porque HF12D repara
el resultado que ese instalador ya dejó aplicado.

## Git

Después de comprobar:

```powershell
Get-ChildItem -Recurse -Filter "*.hf12d.bak" | Remove-Item
git add .
git commit -m "fix: repair model export backend syntax"
git push
```
