# TAHP Pre-Commit Check (Windows PowerShell)
# 在每次提交前执行质量门禁检查
param(
    [switch]$SkipTests = $false,
    [switch]$Verbose = $false
)

$ErrorActionPreference = "Stop"
$exitCode = 0

function Write-Step {
    param([string]$Message, [string]$Color = "Yellow")
    Write-Host "`n$Message" -ForegroundColor $Color
    Write-Host ("-" * 60)
}

Write-Host "`n================================================================" -ForegroundColor Cyan
Write-Host "  TAHP Pre-Commit Quality Gate" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan

# 1. 约束文件验证
Write-Step "[1/4] Constraint File Validation..."
$result = python scripts/validate_constraints.py constraints/ --recursive 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "  FAIL: Constraint validation failed" -ForegroundColor Red
    Write-Host $result
    $exitCode = 1
} else {
    Write-Host "  PASS" -ForegroundColor Green
}

# 2. P0门禁检查
Write-Step "[2/4] P0 Gate Check (telephony)..."
$result = python scripts/gate_check.py constraints/telephony/ --level P0 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "  FAIL: telephony P0 gate check failed" -ForegroundColor Red
    Write-Host $result
    $exitCode = 1
} else {
    Write-Host "  PASS" -ForegroundColor Green
}

Write-Step "[2/4] P0 Gate Check (kernel-driver)..."
$result = python scripts/gate_check.py constraints/kernel-driver/ --level P0 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "  FAIL: kernel-driver P0 gate check failed" -ForegroundColor Red
    Write-Host $result
    $exitCode = 1
} else {
    Write-Host "  PASS" -ForegroundColor Green
}

Write-Step "[2/4] P0 Gate Check (power-mgmt)..."
$result = python scripts/gate_check.py constraints/power-mgmt/ --level P0 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "  FAIL: power-mgmt P0 gate check failed" -ForegroundColor Red
    Write-Host $result
    $exitCode = 1
} else {
    Write-Host "  PASS" -ForegroundColor Green
}

# 3. 单元测试
if (-not $SkipTests) {
    Write-Step "[3/4] Unit Tests (MCP Server)..."
    $result = python -m pytest tahp-mcp-server/ -v --no-header -q 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  FAIL: MCP server tests failed" -ForegroundColor Red
        Write-Host $result
        $exitCode = 1
    } else {
        Write-Host "  PASS" -ForegroundColor Green
    }

    Write-Step "[4/4] Unit Tests (Scripts)..."
    $result = python -m pytest scripts/tests/ -v --no-header -q 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  FAIL: Script tests failed" -ForegroundColor Red
        Write-Host $result
        $exitCode = 1
    } else {
        Write-Host "  PASS" -ForegroundColor Green
    }
} else {
    Write-Host "`n[3/4][4/4] Tests skipped (--SkipTests)" -ForegroundColor DarkYellow
}

# Summary
Write-Host "`n================================================================" -ForegroundColor Cyan
if ($exitCode -eq 0) {
    Write-Host "  ALL CHECKS PASSED" -ForegroundColor Green
} else {
    Write-Host "  SOME CHECKS FAILED — see details above" -ForegroundColor Red
}
Write-Host "================================================================" -ForegroundColor Cyan

exit $exitCode
