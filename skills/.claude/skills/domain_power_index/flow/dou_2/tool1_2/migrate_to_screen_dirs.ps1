# 将高功耗目录根下的 TopN/CPU/AI 产物按亮/灭屏迁入 screen_on、screen_off
param(
    [Parameter(Mandatory = $true)]
    [string]$HighDir,
    [switch]$WhatIf
)

chcp 65001 | Out-Null
$env:PYTHONUTF8 = "1"
$HighDir = (Resolve-Path -LiteralPath $HighDir).Path
$py = Join-Path $PSScriptRoot "migrate_screen_dirs.py"
$args = @($py, $HighDir)
if ($WhatIf) { $args += "--dry-run" }
python @args
