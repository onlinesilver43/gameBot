# Documentation Health Check Script
# Run this script to validate documentation quality and completeness

param(
    [switch]$Fix,
    [switch]$Verbose
)

Write-Host "🔍 Documentation Health Check" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan

$docsPath = Join-Path $PSScriptRoot "..\docs"
$docsPath = Resolve-Path $docsPath

# Check if docs directory exists
if (-not (Test-Path $docsPath)) {
    Write-Host "❌ Docs directory not found at: $docsPath" -ForegroundColor Red
    exit 1
}

$issues = @()
$warnings = @()

# 1. Check for required documentation files
$requiredFiles = @(
    "README.md",
    "ARCHITECTURE.md",
    "TASKS.md",
    "AGENTS.md",
    "ROADMAP.md"
)

Write-Host "`n📁 Checking required files..." -ForegroundColor Yellow
foreach ($file in $requiredFiles) {
    $filePath = Join-Path $docsPath $file
    if (Test-Path $filePath) {
        Write-Host "✅ $file" -ForegroundColor Green
    } else {
        $issues += "Missing required file: $file"
        Write-Host "❌ $file" -ForegroundColor Red
    }
}

# 2. Check for broken internal links
Write-Host "`n🔗 Checking internal links..." -ForegroundColor Yellow
$mdFiles = Get-ChildItem -Path $docsPath -Filter "*.md" -Recurse

foreach ($file in $mdFiles) {
    $content = Get-Content $file.FullName -Raw
    $relativeLinks = [regex]::Matches($content, '\[([^\]]+)\]\(([^)]+\.md)\)')

    foreach ($match in $relativeLinks) {
        $linkPath = $match.Groups[2].Value
        $absolutePath = Join-Path $file.DirectoryName $linkPath
        $absolutePath = [System.IO.Path]::GetFullPath($absolutePath)

        if (-not (Test-Path $absolutePath)) {
            $warnings += "Broken link in $($file.Name): $linkPath"
            Write-Host "⚠️  Broken link in $($file.Name): $linkPath" -ForegroundColor Yellow
        }
    }
}

# 3. Check for outdated TODO items
Write-Host "`n📝 Checking for documentation TODOs..." -ForegroundColor Yellow
foreach ($file in $mdFiles) {
    $content = Get-Content $file.FullName
    $todoLines = $content | Select-String -Pattern "TODO|FIXME|XXX" -CaseSensitive:$false

    if ($todoLines) {
        foreach ($line in $todoLines) {
            $warnings += "TODO found in $($file.Name) line $($line.LineNumber): $($line.Line)"
            if ($Verbose) {
                Write-Host "📝 $($file.Name):$($line.LineNumber) - $($line.Line.Trim())" -ForegroundColor Yellow
            }
        }
        Write-Host "⚠️  $($file.Name) has $($todoLines.Count) TODO items" -ForegroundColor Yellow
    }
}

# 4. Check code documentation in Python files
Write-Host "`n🐍 Checking Python code documentation..." -ForegroundColor Yellow
$pythonFiles = Get-ChildItem -Path (Join-Path $PSScriptRoot "..") -Filter "*.py" -Recurse |
               Where-Object { $_.FullName -notlike "*__pycache__*" -and $_.FullName -notlike "*venv*" }

foreach ($file in $pythonFiles) {
    $content = Get-Content $file.FullName -Raw

    # Check for functions without docstrings
    $functions = [regex]::Matches($content, 'def\s+(\w+)\s*\(')
    foreach ($func in $functions) {
        $funcName = $func.Groups[1].Value
        # Look for docstring after function definition
        $funcIndex = $content.IndexOf("def $funcName(")
        if ($funcIndex -ge 0) {
            $afterFunc = $content.Substring($funcIndex)
            $docstringMatch = [regex]::Match($afterFunc, 'def\s+\w+\s*\([^)]*\)\s*:\s*(["\']{3}|#.*$)')
            if (-not $docstringMatch.Success) {
                $warnings += "Function without docstring: $($file.Name)::$funcName"
            }
        }
    }
}

# 5. Summary
Write-Host "`n📊 Summary" -ForegroundColor Cyan
Write-Host "==========" -ForegroundColor Cyan

if ($issues.Count -eq 0 -and $warnings.Count -eq 0) {
    Write-Host "✅ All checks passed! Documentation looks good." -ForegroundColor Green
} else {
    if ($issues.Count -gt 0) {
        Write-Host "❌ Issues found: $($issues.Count)" -ForegroundColor Red
        foreach ($issue in $issues) {
            Write-Host "  - $issue" -ForegroundColor Red
        }
    }

    if ($warnings.Count -gt 0) {
        Write-Host "⚠️  Warnings: $($warnings.Count)" -ForegroundColor Yellow
        if (-not $Verbose) {
            Write-Host "  Run with -Verbose to see details" -ForegroundColor Gray
        }
    }
}

# Generate report
$reportPath = Join-Path $PSScriptRoot "..\docs-health-report.txt"
if ($Fix -or $issues.Count -gt 0 -or $warnings.Count -gt 0) {
    $report = @"
Documentation Health Report
Generated: $(Get-Date)
Total Issues: $($issues.Count)
Total Warnings: $($warnings.Count)

ISSUES:
$($issues -join "`n")

WARNINGS:
$($warnings -join "`n")
"@

    $report | Out-File -FilePath $reportPath -Encoding UTF8
    Write-Host "`n📄 Report saved to: $reportPath" -ForegroundColor Gray
}

exit ($issues.Count -gt 0 ? 1 : 0)
