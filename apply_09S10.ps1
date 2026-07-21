$ErrorActionPreference = "Stop"

if (-not (Test-Path "app/services/subscription_service.py")) {
    throw "Ejecuta este script desde la raiz del repositorio tryon_backend."
}

python .\apply_09S10.py
python -m compileall app

Write-Host ""
Write-Host "09S10 aplicado correctamente." -ForegroundColor Green
Write-Host "Reinicia el backend y reenvia el evento invoice.paid fallido." -ForegroundColor Yellow
