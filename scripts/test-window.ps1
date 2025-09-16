Param(
    [string]$Title = "Brighter Shores",
    [string]$Template = "assets\\templates\\wendigo.png",
    [string]$Word = "Wendigo",
    [string]$TesseractPath = ""
)

$root = Resolve-Path (Join-Path $PSScriptRoot '..')
$venvPy = Join-Path $root ".venv\\Scripts\\python.exe"
if (-not (Test-Path $venvPy)) { Write-Error "Run scripts\\setup.ps1 first to create the venv"; exit 1 }

Push-Location $root
try {
    if (Test-Path $Template) {
        Write-Host "==> Running template-based detection against window '$Title'" -ForegroundColor Cyan
        & $venvPy -m src.main --test-window --title "$Title" --template "$Template"
    } else {
        Write-Host "==> Template not found; falling back to OCR for '$Word'" -ForegroundColor Yellow
        $argsList = @('-m','src.main','--test-window','--title',"$Title",'--word',"$Word")
        if ($TesseractPath) { $argsList += @('--tesseract-path',"$TesseractPath") }
        & $venvPy @argsList
    }

    if ($LASTEXITCODE -eq 0) {
        Write-Host "Detection succeeded. See window_roi.detected.png" -ForegroundColor Green
    } else {
        Write-Warning "Detection did not confirm. See window_roi.png for the captured ROI."
    }
}
finally { Pop-Location }
