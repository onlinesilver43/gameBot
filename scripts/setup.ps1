Param(
    [string]$PythonVersion = "3.11",
    [string]$TesseractPath = "C:\\Program Files\\Tesseract-OCR\\tesseract.exe",
    [switch]$AddTesseractToPath
)

# Always operate from repo root regardless of where the script is invoked
$root = Resolve-Path (Join-Path $PSScriptRoot '..')
Push-Location $root
try {
    Write-Host "==> Ensuring Python $PythonVersion venv at $($root)\.venv" -ForegroundColor Cyan
    if (-not (Test-Path "$root\.venv")) {
        py -$PythonVersion -m venv "$root\.venv"
    }

    $venvPy = Join-Path $root ".venv\\Scripts\\python.exe"
    if (-not (Test-Path $venvPy)) {
        Write-Error "Venv python not found at $venvPy"; exit 1
    }

    Write-Host "==> Upgrading pip" -ForegroundColor Cyan
    & $venvPy -m pip install --upgrade pip | Out-String | Write-Host

    Write-Host "==> Installing requirements" -ForegroundColor Cyan
    & $venvPy -m pip install -r (Join-Path $root 'requirements.txt') | Out-String | Write-Host

    Write-Host "==> Verifying installed versions" -ForegroundColor Cyan
    Write-Host ("cv2: " + (& $venvPy -c "import cv2; print(cv2.__version__)"))
    Write-Host ("numpy: " + (& $venvPy -c "import numpy; print(numpy.__version__)"))
    Write-Host ("mss: " + (& $venvPy -c "import mss; print(mss.__version__)"))
    if (Test-Path $TesseractPath) {
        $env:TESSERACT_PATH = $TesseractPath
        Write-Host ("tesseract path: " + $TesseractPath)
        try { Write-Host ("tesseract: " + (& $venvPy -c "import pytesseract, os; pytesseract.pytesseract.tesseract_cmd=os.environ.get('TESSERACT_PATH'); print(pytesseract.get_tesseract_version())")) } catch { Write-Warning "pytesseract could not invoke tesseract even though the file exists" }
    } else {
        try { Write-Host ("tesseract: " + (& $venvPy -c "import pytesseract; print(pytesseract.get_tesseract_version())")) } catch { Write-Warning "tesseract not available to pytesseract" }
    }
    Write-Host ("pillow: " + (& $venvPy -c "import PIL; print(PIL.__version__)"))

    Write-Host "==> Tesseract CLI availability" -ForegroundColor Cyan
    try {
        tesseract --version | Select-Object -First 2 | Out-String | Write-Host
    } catch {
        if ($AddTesseractToPath -and (Test-Path $TesseractPath)) {
            Write-Host "==> Adding Tesseract to user PATH" -ForegroundColor Cyan
            $current = [Environment]::GetEnvironmentVariable('Path','User')
            if ($current -notlike "*C:\\Program Files\\Tesseract-OCR*") {
                [Environment]::SetEnvironmentVariable('Path', ($current + ";C:\\Program Files\\Tesseract-OCR"), 'User')
                Write-Host "Added. Restart your terminal for PATH changes to take effect." -ForegroundColor Yellow
            }
        } else {
            Write-Warning "tesseract.exe not found on PATH. Will use TESSERACT_PATH if provided."
        }
    }

    Write-Host "Setup complete." -ForegroundColor Green
}
finally {
    Pop-Location
}
