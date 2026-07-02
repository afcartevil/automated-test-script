# LockNvModify.ps1 - Modify lock card NV macro control in target branch
# Usage: powershell -ExecutionPolicy Bypass -File LockNvModify.ps1 `
#   -TargetBasePath "<target repo public path>" `
#   -BOM_Name_Target "<new BOM name>"
#
# Logic:
#   1. Check NVRAM_EF_SUBSIDY_LOCK_LID_VERNO in l4_nvram_def.h
#      - If value is "001" -> skip entirely (no lock NV modification needed)
#      - If NOT "001" -> proceed with modifications
#   2. Modify 15 locations across 3 files by appending || defined(__{BOM_Name_Target}__)
#      to the first #if defined line after each target macro

param(
    [Parameter(Mandatory=$true)]
    [string]$TargetBasePath,

    [Parameter(Mandatory=$true)]
    [string]$BOM_Name_Target
)

if (-not (Test-Path $TargetBasePath)) {
    @{ success = $false; error = "Target path does not exist: $TargetBasePath" } | ConvertTo-Json -Compress | Write-Output
    exit 1
}

$targetBaseTrimmed = $TargetBasePath.TrimEnd('\')
$macroToAdd = " || defined(__${BOM_Name_Target}__)"

# File paths relative to TargetBasePath
$smlFile = Join-Path $targetBaseTrimmed "mcu\interface\protocol\general\sml_public_def.h"
$l4File = Join-Path $targetBaseTrimmed "mcu\interface\service\nvram\l4_nvram_def.h"
$editorFile = Join-Path $targetBaseTrimmed "mcu\interface\service\nvram\l4_nvram_editor.h"

$details = @()
$modifiedCount = 0
$skippedCount = 0

# --- Helper: Read file with encoding fallback ---
function Read-File {
    param([string]$path)
    try {
        return [System.IO.File]::ReadAllText($path, [System.Text.Encoding]::GetEncoding("GBK"))
    } catch {
        try {
            return Get-Content -Path $path -Raw -Encoding UTF8
        } catch {
            return $null
        }
    }
}

function Write-File {
    param([string]$path, [string]$content)
    try {
        [System.IO.File]::WriteAllText($path, $content, [System.Text.Encoding]::GetEncoding("GBK"))
        return $true
    } catch {
        return $false
    }
}

# --- Helper: Check if file already contains the target BOM ---
function Test-AlreadyModified {
    param([string]$content)
    return ($content -match "defined\($([regex]::Escape("__${BOM_Name_Target}__"))\)")
}

# --- Helper: Find target macro and the first #if defined line after it ---
# Returns: @{ targetIdx=N; ifLineIdx=M } or -1 if not found
function Find-IfLineAfterTarget {
    param(
        [string[]]$lines,
        [string]$targetMacro,
        [int]$startIndex = 0
    )
    # Find the target macro line (loose match)
    $targetIdx = -1
    for ($i = $startIndex; $i -lt $lines.Count; $i++) {
        $normalizedLine = ($lines[$i].Trim() -replace '\s+', ' ')
        $normalizedTarget = ($targetMacro.Trim() -replace '\s+', ' ')
        if ($normalizedLine.Contains($normalizedTarget)) {
            $targetIdx = $i
            break
        }
    }
    if ($targetIdx -lt 0) { return -1 }

    # Find the first #if defined line after the target macro line
    for ($i = $targetIdx + 1; $i -lt $lines.Count; $i++) {
        $line = $lines[$i].TrimStart()
        if ($line -match '^#\s*if\s+defined\(') {
            return @{ targetIdx = $targetIdx; ifLineIdx = $i }
        }
    }
    return -1  # No #if defined found
}

# ============================================================
# STEP 1: Pre-check - Verify NVRAM_EF_SUBSIDY_LOCK_LID_VERNO
# ============================================================
if (-not (Test-Path $l4File)) {
    @{
        success = $false
        error = "l4_nvram_def.h not found: $l4File"
        skipped = $true
        reason = "Target file does not exist"
    } | ConvertTo-Json -Depth 3 | Write-Output
    exit 0
}

$l4Content = Read-File -path $l4File
if ($null -eq $l4Content) {
    @{
        success = $false
        error = "Failed to read l4_nvram_def.h"
    } | ConvertTo-Json -Compress | Write-Output
    exit 1
}

# Extract the value of NVRAM_EF_SUBSIDY_LOCK_LID_VERNO
# The macro may appear in multiple #if/#else blocks
# If ANY definition is NOT "001", the project needs lock NV modification
$subsidyLines = [regex]::Matches($l4Content, '#define\s+NVRAM_EF_SUBSIDY_LOCK_LID_VERNO\s+"([^"]+)"')
$allValues = @()
foreach ($m in $subsidyLines) {
    $allValues += $m.Groups[1].Value
}

# Check if ALL definitions are "001" — only then skip
$allAre001 = ($allValues.Count -gt 0) -and ($allValues | Where-Object { $_ -ne "001" }).Count -eq 0
if ($allAre001) {
    @{
        success = $true
        message = "NVRAM_EF_SUBSIDY_LOCK_LID_VERNO all values are `"001`", no lock NV modification needed"
        skipped = $true
        reason = "Subsidy lock not enabled (VERNO=001)"
        subsidyLockLidVerno = ($allValues -join ", ")
        modifiedCount = 0
        skippedCount = 0
        details = @()
    } | ConvertTo-Json -Depth 3 | Write-Output
    exit 0
}

# If any definition is NOT "001", proceed with modifications
$primaryValue = $allValues[0]
Write-Output "NVRAM_EF_SUBSIDY_LOCK_LID_VERNO values found: $($allValues -join ', ') — proceeding with modifications"

# ============================================================
# STEP 2: Define modification targets
# ============================================================
$smlTargetMacros = @(
    "#define SML_SL_BLOB_TIME_STAMP_SIZE             8",
    "#define SML_SL_BLOB_LENGTH_SIZE                 2",
    "#define SML_SL_BLOB_SIZE_OF_SIGNATURE           256",
    "#define SML_SL_NVRAM_ACCESS_ID_UPDATE_LOCK_OP   0xFB",
    "#define SML_SL_BLOB_SIZE_OF_CAT_SP     7",
    "#define SML_SL_BLOB_MAX_SUPPORT_CAT_SP     10",
    "#define SML_SL_BLOB_CAT_SP_SIZE         (SML_SL_BLOB_MAX_SUPPORT_CAT_SP * SML_SL_BLOB_SIZE_OF_CAT_SP)",
    "kal_uint8   time_stamp[SML_SL_BLOB_TIME_STAMP_SIZE];",
    "kal_uint8   code_cat_sp[SML_SL_BLOB_CAT_SP_SIZE];",
    "kal_uint8   signature[SML_SL_BLOB_SIZE_OF_SIGNATURE];"
)

$l4TargetMacros = @(
    '#define NVRAM_EF_SML_S_LID_VERNO    "001"',
    '#define NVRAM_EF_SML_S_LID_HASH   0x4E0B7529'
)

$editorTargetMacros = @(
    'time_stamp:"[DOC, RUNTIME]Time stamp value in BLOB"',
    'code_cat_sp:"[DOC, RUNTIME]Service Provider Configuration code: MCC-MNC-GID triplets"',
    'signature:"[DOC, RUNTIME]Signature: Verification code used for blob validation"'
)

# ============================================================
# STEP 3: Process each file
# ============================================================
$fileConfigs = @(
    @{ path = $smlFile; macros = $smlTargetMacros; name = "sml_public_def.h" },
    @{ path = $l4File; macros = $l4TargetMacros; name = "l4_nvram_def.h" },
    @{ path = $editorFile; macros = $editorTargetMacros; name = "l4_nvram_editor.h" }
)

foreach ($config in $fileConfigs) {
    $filePath = $config.path
    $fileName = $config.name
    $macros = $config.macros

    $fileDetail = @{
        file = $fileName
        path = $filePath
        changes = 0
        status = ""
        modifications = @()
    }

    if (-not (Test-Path $filePath)) {
        $fileDetail.status = "SKIPPED_FILE_NOT_FOUND"
        $skippedCount++
        $details += $fileDetail
        continue
    }

    $content = Read-File -path $filePath
    if ($null -eq $content) {
        $fileDetail.status = "SKIPPED_READ_ERROR"
        $skippedCount++
        $details += $fileDetail
        continue
    }

    # Check if already fully modified
    if (Test-AlreadyModified -content $content) {
        $fileDetail.status = "SKIPPED_ALREADY_MODIFIED"
        $fileDetail.message = "File already contains $BOM_Name_Target macro control"
        $skippedCount++
        $details += $fileDetail
        continue
    }

    $lines = $content -split "`n" | ForEach-Object { $_.TrimEnd("`r") }
    $fileModified = $false
    $fileChanges = 0

    foreach ($macro in $macros) {
        $findResult = Find-IfLineAfterTarget -lines $lines -targetMacro $macro

        $modDetail = @{
            targetMacro = $macro
            status = ""
        }

        if ($findResult -eq -1) {
            $modDetail.status = "NOT_FOUND"
            $skippedCount++
        } elseif ($findResult -is [hashtable]) {
            $ifLineIdx = $findResult.ifLineIdx
            # Check if already contains our macro
            if ($lines[$ifLineIdx] -match [regex]::Escape($macroToAdd)) {
                $modDetail.status = "ALREADY_MODIFIED"
                $skippedCount++
            } else {
                # Do the actual modification in the caller's scope
                $commentIdx = $lines[$ifLineIdx].IndexOf("//")
                if ($commentIdx -gt 0) {
                    $codePart = $lines[$ifLineIdx].Substring(0, $commentIdx).TrimEnd()
                    $commentPart = $lines[$ifLineIdx].Substring($commentIdx)
                    $lines[$ifLineIdx] = $codePart + $macroToAdd + " " + $commentPart
                } else {
                    $lines[$ifLineIdx] = $lines[$ifLineIdx] + $macroToAdd
                }
                $modDetail.status = "MODIFIED"
                $modDetail.lineNumber = $ifLineIdx + 1
                $fileChanges++
                $modifiedCount++
            }
        } else {
            $modDetail.status = "NOT_FOUND"
            $skippedCount++
        }

        $fileDetail.modifications += $modDetail
    }

    if ($fileChanges -gt 0) {
        $newContent = ($lines -join "`n")
        $writeOk = Write-File -path $filePath -content $newContent
        if ($writeOk) {
            $fileDetail.status = "MODIFIED"
            $fileDetail.changes = $fileChanges
        } else {
            $fileDetail.status = "FAILED_WRITE"
            $fileDetail.message = "Failed to write file"
        }
    } else {
        $fileDetail.status = "NO_CHANGES"
    }

    $details += $fileDetail
}

# ============================================================
# STEP 4: Return results
# ============================================================
$result = @{
    success = $true
    message = "Lock NV modification completed"
    subsidyLockLidVerno = $primaryValue
    modifiedCount = $modifiedCount
    skippedCount = $skippedCount
    details = $details
}

$result | ConvertTo-Json -Depth 5 | Write-Output
