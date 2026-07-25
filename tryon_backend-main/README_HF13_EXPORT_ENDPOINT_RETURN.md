# HF13 Backend — Return correcto del exportador

Corrige el error:

```text
fastapi.exceptions.ResponseValidationError
Input should be a valid dictionary or object
input: None
```

La función `export_models_volume` declaraba un `response_model`, pero terminaba
sin devolver el trabajo creado. FastAPI intentaba validar `None`.

El parche garantiza:

```python
return RuntimeContextJobService.public(job["job_id"])
```

## Aplicación

```powershell
python apply_hf13_export_endpoint_return.py
python -m compileall app
uvicorn app.main:app --reload --port 8001
```

No vuelvas a ejecutar los instaladores HF12 anteriores.

## Git

```powershell
Get-ChildItem -Recurse -Filter "*.hf13.bak" | Remove-Item
git add .
git commit -m "fix: return model export job from endpoint"
git push
```
