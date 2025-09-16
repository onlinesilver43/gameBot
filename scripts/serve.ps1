Param(
    [int]$Port = 8083,
    [ValidateSet('DEBUG','INFO','WARNING','ERROR','CRITICAL')][string]$LogLevel = 'INFO',
    [string]$TesseractPath = ''
)

$root = Resolve-Path (Join-Path $PSScriptRoot '..')
$venvPy = Join-Path $root ".venv\\Scripts\\python.exe"
if (-not (Test-Path $venvPy)) { Write-Error "Run scripts\\setup.ps1 first to create the venv"; exit 1 }

Push-Location $root
try {
    $env:PORT = "$Port"
    $env:LOG_LEVEL = "$LogLevel"
    if ($TesseractPath) { $env:TESSERACT_PATH = $TesseractPath }
    Write-Host "Serving UI on http://127.0.0.1:$Port" -ForegroundColor Green
    & $venvPy -m bsbot.ui.server
}
finally { Pop-Location }
