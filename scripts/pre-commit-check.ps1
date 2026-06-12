# TAHP Pre-Commit Check — tahp-console tests only
param(
    [switch]$SkipTests = $false
)

$ErrorActionPreference = "Stop"
$exitCode = 0

Write-Host "`nTAHP Pre-Commit: tahp-console" -ForegroundColor Cyan

if (-not $SkipTests) {
    Push-Location (Join-Path $PSScriptRoot "..\tahp-console")
    try {
        npm test
        if ($LASTEXITCODE -ne 0) { $exitCode = 1 }
    } finally {
        Pop-Location
    }
} else {
    Write-Host "Tests skipped (--SkipTests)" -ForegroundColor DarkYellow
}

exit $exitCode
