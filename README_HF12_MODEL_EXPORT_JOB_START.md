# HF12 Backend — Exportador de modelos observable

## Corrección

El endpoint de exportación ya no deja el inicio del trabajo sujeto a
`BackgroundTasks`. Ahora:

1. crea el trabajo;
2. lo marca como `starting` con progreso inicial;
3. inicia un hilo daemon independiente;
4. devuelve inmediatamente el `202`;
5. permite que el BackOffice consulte el progreso desde el primer instante.

## Aplicación

Descomprime directamente en la raíz de `tryon_backend`:

```powershell
python apply_hf12_model_export_job_start.py
python -m compileall app
uvicorn app.main:app --reload --port 8001
```

## Git

Después de probar:

```powershell
Get-ChildItem -Recurse -Filter "*.hf12.bak" | Remove-Item
git add .
git commit -m "fix: start model export jobs immediately"
git push
```
