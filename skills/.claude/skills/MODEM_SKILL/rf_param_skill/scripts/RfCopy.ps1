# RF parameter file copy script
# Usage: powershell -ExecutionPolicy Bypass -File RfCopy.ps1 -SourcePath "<src>" -TargetPath "<dst>"
# Output: JSON result

param(
    [Parameter(Mandatory=$true)]
    [string]$SourcePath,

    [Parameter(Mandatory=$true)]
    [string]$TargetPath
)

if (-not (Test-Path $SourcePath)) {
    @{
        success = $false
        error = "Source path does not exist: $SourcePath"
        error_code = "SOURCE_PATH_NOT_FOUND"
    } | ConvertTo-Json -Compress | Write-Output
    exit 1
}

$hasIni = (Get-ChildItem -Path $SourcePath -File -Filter "*.ini" -ErrorAction SilentlyContinue).Count -gt 0
$hasCfg = (Get-ChildItem -Path $SourcePath -File -Filter "*.cfg" -ErrorAction SilentlyContinue).Count -gt 0
$hasMcu = Test-Path (Join-Path $SourcePath "mcu")

if (-not ($hasIni -or $hasCfg -or $hasMcu)) {
    @{
        success = $false
        error = "No .ini/.cfg/mcu found in source directory"
        error_code = "INVALID_RF_PROJECT"
    } | ConvertTo-Json -Compress | Write-Output
    exit 1
}

if (-not (Test-Path $TargetPath)) {
    New-Item -Path $TargetPath -ItemType Directory -Force | Out-Null
    Write-Host "[RfCopy] Created target directory: $TargetPath"
}

Write-Host "[RfCopy] Copying: $SourcePath -> $TargetPath"

# Try robocopy first (without /DCOPY to avoid network drive attribute errors)
robocopy $SourcePath $TargetPath /E /R:3 /W:5 /NP /NJH /NJS /COPY:DAT | Out-Null
$robocopyExit = $LASTEXITCODE

$targetCountAfterRobo = (Get-ChildItem -Path $TargetPath -Recurse -File -ErrorAction SilentlyContinue).Count
$sourceCount = (Get-ChildItem -Path $SourcePath -Recurse -File).Count

Write-Host "[RfCopy] robocopy exit: $robocopyExit, source: $sourceCount, target: $targetCountAfterRobo"

# If robocopy did not copy all files, fall back to Copy-Item
if ($targetCountAfterRobo -ne $sourceCount) {
    Write-Host "[RfCopy] robocopy did not copy all files, falling back to Copy-Item..."

    # Clean target directory
    if ($targetCountAfterRobo -gt 0) {
        Get-ChildItem -Path $TargetPath -Recurse -File | Remove-Item -Force
        Get-ChildItem -Path $TargetPath -Directory | Where-Object { $_.FullName -ne $TargetPath } | Remove-Item -Recurse -Force
    }

    # Use Copy-Item for recursive copy
    Get-ChildItem -Path $SourcePath -Recurse -File | ForEach-Object {
        $relativePath = $_.FullName.Substring($SourcePath.Length).TrimStart('\')
        $destFile = Join-Path $TargetPath $relativePath
        $destDir = Split-Path $destFile -Parent
        if (-not (Test-Path $destDir)) {
            New-Item -Path $destDir -ItemType Directory -Force | Out-Null
        }
        Copy-Item -Path $_.FullName -Destination $destFile -Force
    }

    $targetCountAfterCopy = (Get-ChildItem -Path $TargetPath -Recurse -File).Count
    Write-Host "[RfCopy] Copy-Item done, target: $targetCountAfterCopy"
} else {
    $targetCountAfterCopy = $targetCountAfterRobo
}

# Verification
$targetCount = (Get-ChildItem -Path $TargetPath -Recurse -File).Count
Write-Host "[RfCopy] Final: source $sourceCount, target $targetCount"

$missingIni = @()
Get-ChildItem -Path $SourcePath -File -Filter "*.ini" -ErrorAction SilentlyContinue | ForEach-Object {
    if (-not (Test-Path (Join-Path $TargetPath $_.Name))) {
        $missingIni += $_.Name
        Write-Host "[RfCopy] Missing .ini: $($_.Name)"
    }
}

$missingCfg = @()
Get-ChildItem -Path $SourcePath -File -Filter "*.cfg" -ErrorAction SilentlyContinue | ForEach-Object {
    if (-not (Test-Path (Join-Path $TargetPath $_.Name))) {
        $missingCfg += $_.Name
        Write-Host "[RfCopy] Missing .cfg: $($_.Name)"
    }
}

$missingMcu = $false
if (Test-Path (Join-Path $SourcePath "mcu")) {
    $sourceMcuCount = (Get-ChildItem -Path (Join-Path $SourcePath "mcu") -Recurse -File -ErrorAction SilentlyContinue).Count
    $targetMcuPath = Join-Path $TargetPath "mcu"
    if (-not (Test-Path $targetMcuPath)) {
        $missingMcu = $true
        Write-Host "[RfCopy] Missing mcu directory"
    } else {
        $targetMcuCount = (Get-ChildItem -Path $targetMcuPath -Recurse -File -ErrorAction SilentlyContinue).Count
        if ($sourceMcuCount -ne $targetMcuCount) {
            $missingMcu = $true
            Write-Host "[RfCopy] mcu count mismatch: source $sourceMcuCount, target $targetMcuCount"
        }
    }
}

# Supplemental copy for missing files
$supplementalCopied = 0

if ($missingIni.Count -gt 0) {
    foreach ($iniName in $missingIni) {
        Copy-Item -Path (Join-Path $SourcePath $iniName) -Destination $TargetPath -Force
        $supplementalCopied++
        Write-Host "[RfCopy] Copied .ini: $iniName"
    }
}

if ($missingCfg.Count -gt 0) {
    foreach ($cfgName in $missingCfg) {
        Copy-Item -Path (Join-Path $SourcePath $cfgName) -Destination $TargetPath -Force
        $supplementalCopied++
        Write-Host "[RfCopy] Copied .cfg: $cfgName"
    }
}

if ($missingMcu) {
    $mcuSrc = Join-Path $SourcePath "mcu"
    $mcuDst = Join-Path $TargetPath "mcu"
    Get-ChildItem -Path $mcuSrc -Recurse -File | ForEach-Object {
        $relativePath = $_.FullName.Substring($mcuSrc.Length).TrimStart('\')
        $destFile = Join-Path $mcuDst $relativePath
        $destDir = Split-Path $destFile -Parent
        if (-not (Test-Path $destDir)) {
            New-Item -Path $destDir -ItemType Directory -Force | Out-Null
        }
        Copy-Item -Path $_.FullName -Destination $destFile -Force
    }
    $supplementalCopied++
    Write-Host "[RfCopy] Copied mcu directory"
}

# Final verification
$finalTargetCount = (Get-ChildItem -Path $TargetPath -Recurse -File).Count
$allMatch = ($finalTargetCount -eq $sourceCount)

$result = @{
    success = $allMatch
    source_path = $SourcePath
    target_path = $TargetPath
    source_file_count = $sourceCount
    target_file_count = $finalTargetCount
    files_match = $allMatch
    ini_verified = ($missingIni.Count -eq 0 -or $supplementalCopied -ge $missingIni.Count)
    cfg_verified = ($missingCfg.Count -eq 0 -or $supplementalCopied -ge $missingCfg.Count)
    mcu_verified = (-not $missingMcu)
    missing_files = @{
        ini = $missingIni
        cfg = $missingCfg
        mcu = $missingMcu
    }
    supplemental_copied = $supplementalCopied
    robocopy_exit_code = $robocopyExit
    used_fallback = ($targetCountAfterRobo -ne $sourceCount)
}

if (-not $allMatch) {
    $result.error = "File count still mismatch: source $sourceCount, target $finalTargetCount"
    $result.error_code = "FILE_COUNT_MISMATCH"
}

$result | ConvertTo-Json -Depth 3 | Write-Output

if (-not $allMatch) { exit 1 }
exit 0
