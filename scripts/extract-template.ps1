Param(
    [Parameter(Mandatory=$true)][string]$Screenshot,
    [string]$Template = "assets\\templates\\wendigo.png"
)

$root = Resolve-Path (Join-Path $PSScriptRoot '..')
$venvPy = Join-Path $root ".venv\\Scripts\\python.exe"
if (-not (Test-Path $venvPy)) { Write-Error "Run scripts\\setup.ps1 first to create the venv"; exit 1 }
if (-not (Test-Path $Screenshot)) { Write-Error "Screenshot not found: $Screenshot"; exit 1 }

Push-Location $root
try {
    Write-Host "==> Extracting template from screenshot" -ForegroundColor Cyan
    & $venvPy -m bsbot.tools.detect_cli --save-template-from "$Screenshot" --template "$Template"
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Saved template to $Template" -ForegroundColor Green
    } else {
        Write-Warning "Template extraction failed. Check output above."
    }
}
finally { Pop-Location }
