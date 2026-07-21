$ErrorActionPreference = "Stop"

if (-not (Test-Path "app/services/billing_invoice_service.py")) {
    throw "Ejecuta este script desde la raiz del repositorio tryon_backend."
}

python .\apply_09S11.py
python -m compileall app

Write-Host ""
Write-Host "09S11 aplicado correctamente." -ForegroundColor Green
Write-Host "Reinicia el backend y reenvia invoice.paid." -ForegroundColor Yellow
