$ErrorActionPreference = "Stop"
python tools/apply_stripe_invoice_hardening.py
python -m compileall app
Write-Host "09S19 aplicado y backend compilado correctamente." -ForegroundColor Green
