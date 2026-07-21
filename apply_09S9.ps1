$ErrorActionPreference = "Stop"

if (-not (Test-Path "app/services/billing_service.py")) {
    throw "Ejecuta este script desde la raiz del repositorio tryon_backend."
}

python .\apply_09S9.py
python -m compileall app

Write-Host ""
Write-Host "09S9 aplicado correctamente." -ForegroundColor Green
