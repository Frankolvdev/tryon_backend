$ErrorActionPreference = "Stop"
$backend = "F:\PROYECTOS PERSONALES\TRYON\backend"
$source = Join-Path $PSScriptRoot "app\core\config.py"
$target = Join-Path $backend "app\core\config.py"
Copy-Item $source $target -Force
Write-Host "Reemplazado: $target"
Select-String -Path $target -Pattern "TEST_FORCE_BILLING_OVERRUN|TEST_BILLING_USER_ID|TEST_BILLING_EXECUTION_ID"
