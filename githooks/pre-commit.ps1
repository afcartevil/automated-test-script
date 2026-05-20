# TAHP pre-commit hook (Windows PowerShell 版本)
# 约束文件变更必须更新 changelog
#
# 安装方式:
#   git config core.hooksPath githooks
#   (Git for Windows 会自动调用 .ps1 文件)

$changedConstraints = git diff --cached --name-only | Select-String -Pattern '^constraints/.*\.ya?ml$' | Where-Object { $_ -notmatch 'module\.yaml' }

if (-not $changedConstraints) {
    exit 0
}

$hasError = $false

foreach ($file in $changedConstraints) {
    $file = $file.ToString().Trim()
    $diff = git diff --cached $file
    if ($diff -match 'changelog') {
        continue
    }
    Write-Host "ERROR: $file 变更但未更新 metadata.changelog 字段" -ForegroundColor Red
    Write-Host "  请在 metadata 段中添加 changelog 条目，记录变更原因、日期和作者。" -ForegroundColor Yellow
    Write-Host ""
    $hasError = $true
}

if ($hasError) {
    Write-Host "---" -ForegroundColor DarkGray
    Write-Host "提示：如果这是首次创建或批量修复文件，可以使用 --no-verify 跳过本次检查。" -ForegroundColor Cyan
    exit 1
}

exit 0
