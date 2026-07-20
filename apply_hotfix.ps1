$ErrorActionPreference = "Stop"

$target = Join-Path $PSScriptRoot "app\services\user_service.py"

if (-not (Test-Path $target)) {
    throw "No se encontró $target. Descomprime este ZIP directamente en la raíz de tryon_backend."
}

$content = Get-Content -Raw -Encoding UTF8 $target

if ($content -match 'user_dict\.pop\(\s*["'']turnstile_token["'']') {
    Write-Host "El hotfix ya está aplicado en user_service.py." -ForegroundColor Yellow
    exit 0
}

$pattern = '(?m)^(?<indent>[ \t]*)user\s*=\s*user_repository\.create\('
$match = [regex]::Match($content, $pattern)

if (-not $match.Success) {
    throw "No se encontró la llamada user_repository.create(...) en app/services/user_service.py. No se modificó el archivo."
}

$indent = $match.Groups["indent"].Value
$insertion = @"
${indent}# Campo temporal de validación anti-bot; no pertenece al modelo SQLAlchemy User.
${indent}user_dict.pop("turnstile_token", None)

"@

$backup = "$target.before_turnstile_hotfix"
Copy-Item $target $backup -Force

$content = $content.Insert($match.Index, $insertion)
Set-Content -Path $target -Value $content -Encoding UTF8

$verify = Get-Content -Raw -Encoding UTF8 $target
if ($verify -notmatch 'user_dict\.pop\(\s*["'']turnstile_token["'']') {
    Copy-Item $backup $target -Force
    throw "La verificación automática falló. Se restauró el archivo original."
}

Write-Host "Hotfix aplicado correctamente." -ForegroundColor Green
Write-Host "Archivo modificado: app\services\user_service.py"
Write-Host "Respaldo creado: app\services\user_service.py.before_turnstile_hotfix"
Write-Host ""
Write-Host "Bloque agregado antes de user_repository.create(...):"
Write-Host 'user_dict.pop("turnstile_token", None)'
