# ApplyGpioDifferences.ps1 - Apply all differences from source to target
# All differences are resolved in favor of the SOURCE file.
# Handles: GPIO configs, md1_eint module, ADC (DRDI) configuration
#
# Usage: powershell -ExecutionPolicy Bypass -File ApplyGpioDifferences.ps1 `
#   -SourcePath "<source .dws file>" `
#   -TargetPath "<target .dws file>" `
#   -GpioNums "103,111,114,115,..."

param(
    [Parameter(Mandatory=$true)]
    [string]$SourcePath,

    [Parameter(Mandatory=$true)]
    [string]$TargetPath,

    [Parameter(Mandatory=$true)]
    [string]$GpioNums
)

$result = @{
    success = $false
    message = ""
    applied = @()
    deleted = @()
    md1_eint_applied = $false
    adc_applied = $false
}

# Validate paths
if (-not (Test-Path $SourcePath)) {
    $result.message = "Source file not found: $SourcePath"
    $result | ConvertTo-Json -Depth 3 | Write-Output
    exit 1
}
if (-not (Test-Path $TargetPath)) {
    $result.message = "Target file not found: $TargetPath"
    $result | ConvertTo-Json -Depth 3 | Write-Output
    exit 1
}

# Read files
$sourceContent = Get-Content -Path $SourcePath -Raw -Encoding UTF8
$targetContent = Get-Content -Path $TargetPath -Raw -Encoding UTF8

$modifiedCount = 0
$deletedCount = 0

# Detect source GPIO leading indent for preserving formatting
$sourceIndent = ""
$srcIndentMatch = [regex]::Match($sourceContent, '(\s*)<gpio\d+>')
if ($srcIndentMatch.Success) {
    $srcLeadWs = $srcIndentMatch.Groups[1].Value
    $srcLastNl = $srcLeadWs.LastIndexOf("`n")
    $sourceIndent = if ($srcLastNl -ge 0) { $srcLeadWs.Substring($srcLastNl + 1) } else { "" }
}

# ============================================================
# PART 1: Apply GPIO differences
# ============================================================
$gpioNumsArray = $GpioNums -split "," | ForEach-Object { $_.Trim() } | Where-Object { $_ -match "^\d+$" } | ForEach-Object { [int]$_ } | Sort-Object

foreach ($gpioNum in $gpioNumsArray) {
    $sourcePattern = "(\s*)<gpio$gpioNum>([\s\S]*?)</gpio$gpioNum>"
    $targetPattern = "(\s*)<gpio$gpioNum>([\s\S]*?)</gpio$gpioNum>"

    $sourceMatch = [regex]::Match($sourceContent, $sourcePattern)
    $targetMatch = [regex]::Match($targetContent, $targetPattern)

    # Extract source inner content and indent
    $sourceInner = if ($sourceMatch.Success) { $sourceMatch.Groups[2].Value } else { "" }
    $sourceIndent = if ($sourceMatch.Success) {
        $slws = $sourceMatch.Groups[1].Value
        $slnl = $slws.LastIndexOf("`n")
        if ($slnl -ge 0) { $slws.Substring($slnl + 1) } else { "" }
    } else { "" }

    if ($sourceMatch.Success -and -not $targetMatch.Success) {
        # Source has, target doesn't → copy from source to target (preserve indentation)
        $newBlock = "${sourceIndent}<gpio$gpioNum>${sourceInner}`n${sourceIndent}</gpio$gpioNum>"
        $allGpios = [regex]::Matches($targetContent, '(\s*)<gpio(\d+)>')
        $existingNums = $allGpios | ForEach-Object { [int]$_.Groups[2].Value } | Sort-Object
        $insertBefore = $null
        $targetIndent = $sourceIndent
        foreach ($m in $allGpios) {
            $n = [int]$m.Groups[2].Value
            if ($n -gt $gpioNum) {
                $insertBefore = $n
                # Detect target's GPIO indent
                $tLeadWs = $m.Groups[1].Value
                $tLastNl = $tLeadWs.LastIndexOf("`n")
                $targetIndent = if ($tLastNl -ge 0) { $tLeadWs.Substring($tLastNl + 1) } else { "" }
                break
            }
        }
        # Rebuild newBlock with target indent if available
        $newBlock = "${targetIndent}<gpio$gpioNum>${sourceInner}`n${targetIndent}</gpio$gpioNum>"
        if ($insertBefore) {
            $targetContent = $targetContent.Replace("<gpio$insertBefore>", "`n$newBlock`n${targetIndent}<gpio$insertBefore>")
        } else {
            $targetContent = $targetContent + "`n" + $newBlock
        }
        Write-Output "GPIO${gpioNum}: Added to target (copied from source)"
        $result.applied += @{ gpioNum = "$gpioNum"; action = "added" }
        $modifiedCount++

    } elseif ($sourceMatch.Success -and $targetMatch.Success) {
        # Both have but config differs → replace target with source (preserve target indentation)
        $targetLeadWs = $targetMatch.Groups[1].Value
        $targetLastNl = $targetLeadWs.LastIndexOf("`n")
        $targetGpioIndent = if ($targetLastNl -ge 0) { $targetLeadWs.Substring($targetLastNl + 1) } else { "" }
        $replacement = "${targetGpioIndent}<gpio$gpioNum>${sourceInner}`n${targetGpioIndent}</gpio$gpioNum>"
        $targetContent = $targetContent -replace "(\s*)<gpio$gpioNum>[\s\S]*?</gpio$gpioNum>", $replacement
        Write-Output "GPIO${gpioNum}: Replaced target config with source config"
        $result.applied += @{ gpioNum = "$gpioNum"; action = "replaced" }
        $modifiedCount++

    } elseif (-not $sourceMatch.Success -and $targetMatch.Success) {
        # Source doesn't have, target does → delete from target
        $targetContent = $targetContent -replace "<gpio$gpioNum>[\s\S]*?</gpio$gpioNum>\s*", ""
        Write-Output "GPIO${gpioNum}: Deleted from target (not in source)"
        $result.deleted += "$gpioNum"
        $deletedCount++
    }
}

# ============================================================
# PART 2: Apply md1_eint module difference
# ============================================================
$md1Pattern = '(<module name="md1_eint">[\s\S]*?</module>)'
$md1Match_C = [regex]::Match($sourceContent, $md1Pattern)
$md1Match_D = [regex]::Match($targetContent, $md1Pattern)

if ($md1Match_C.Success -and $md1Match_D.Success) {
    # Both have md1_eint, check if they differ
    $configC = $md1Match_C.Groups[1].Value -replace '\s+', ' '
    $configD = $md1Match_D.Groups[1].Value -replace '\s+', ' '
    if ($configC -ne $configD) {
        # Replace target md1_eint with source
        $targetContent = $targetContent -replace $md1Pattern, $md1Match_C.Groups[1].Value
        Write-Output "md1_eint: Replaced target config with source config"
        $result.md1_eint_applied = $true
        $modifiedCount++
    }
} elseif ($md1Match_C.Success -and -not $md1Match_D.Success) {
    # Source has md1_eint, target doesn't → insert before next module or end of general
    $modulePattern = '(<module name="[^"]+">[\s\S]*?</module>)'
    $firstModule = [regex]::Match($targetContent, '<module name="[^"]+">')
    if ($firstModule.Success) {
        $targetContent = $targetContent.Replace($firstModule.Value, $md1Match_C.Groups[1].Value + "`n" + $firstModule.Value)
    } else {
        $targetContent = $targetContent -replace '(</general>)', $md1Match_C.Groups[1].Value + "`n`$1"
    }
    Write-Output "md1_eint: Added to target (copied from source)"
    $result.md1_eint_applied = $true
    $modifiedCount++
} elseif (-not $md1Match_C.Success -and $md1Match_D.Success) {
    # Source doesn't have md1_eint, target does → delete from target
    $targetContent = $targetContent -replace "$md1Pattern\s*", ""
    Write-Output "md1_eint: Deleted from target (not in source)"
    $result.md1_eint_applied = $true
    $deletedCount++
}

# ============================================================
# PART 3: Apply ADC (DRDI) configuration difference
# ============================================================
# Check if both files have the ADC config
$adcPattern = '<varName>ADC_FDD_RF_PARAMS_DYNAMIC_CUSTOM_CH</varName>'
$adcMatch_C = [regex]::Match($sourceContent, $adcPattern)
$adcMatch_D = [regex]::Match($targetContent, $adcPattern)

if ($adcMatch_C.Success -and $adcMatch_D.Success) {
    # Both have ADC config, check if ADC number matches
    $adcBlocks_C = [regex]::Matches($sourceContent, '(<adc(\d+)>[\s\S]*?</adc\2>)')
    $adcBlocks_D = [regex]::Matches($targetContent, '(<adc(\d+)>[\s\S]*?</adc\2>)')
    $cBlock = $null; $dBlock = $null; $cNum = $null; $dNum = $null
    foreach ($b in $adcBlocks_C) { if ($b.Groups[2].Value -match 'ADC_FDD_RF_PARAMS_DYNAMIC_CUSTOM_CH') { $cBlock = $b.Groups[1].Value; $cNum = $b.Groups[3].Value; break } }
    foreach ($b in $adcBlocks_D) { if ($b.Groups[2].Value -match 'ADC_FDD_RF_PARAMS_DYNAMIC_CUSTOM_CH') { $dBlock = $b.Groups[1].Value; $dNum = $b.Groups[3].Value; break } }
    if ($cBlock -and $dBlock -and $cNum -ne $dNum) {
        # ADC number differs → replace target's ADC block with source's
        $targetContent = $targetContent.Replace($dBlock, $cBlock)
        Write-Output "ADC: Replaced target adc${dNum} with source adc${cNum}"
        $result.adc_applied = $true
        $modifiedCount++
    }
} elseif ($adcMatch_C.Success -and -not $adcMatch_D.Success) {
    # Source has ADC config, target doesn't → copy from source to target
    $adcBlocks_C = [regex]::Matches($sourceContent, '(<adc(\d+)>[\s\S]*?</adc\2>)')
    $adcNumPattern = '<count>(\d+)</count>'
    $adcModule_C = [regex]::Match($sourceContent, '(<module name="adc">[\s\S]*?</module>)')
    if ($adcModule_C.Success) {
        # Insert ADC module into target's general section before next module or after clk
        $generalMatch = [regex]::Match($targetContent, '(<general[\s\S]*?>)')
        if ($generalMatch.Success) {
            $insertAfter = $generalMatch.Groups[1].Value
            $targetContent = $targetContent.Replace($insertAfter, $insertAfter + "`n" + $adcModule_C.Groups[1].Value)
            Write-Output "ADC: Added ADC module to target (copied from source)"
            $result.adc_applied = $true
            $modifiedCount++
        }
    }
} elseif (-not $adcMatch_C.Success -and $adcMatch_D.Success) {
    # Source doesn't have ADC config, target does → delete from target
    $targetContent = $targetContent -replace '<module name="adc">[\s\S]*?</module>\s*', ''
    Write-Output "ADC: Deleted ADC module from target (not in source)"
    $result.adc_applied = $true
    $deletedCount++
}

# ============================================================
# Write modified content back to target file
# ============================================================
try {
    Set-Content -Path $TargetPath -Value $targetContent -NoNewline -Encoding UTF8
    $result.success = $true
    $result.message = "Applied $modifiedCount change(s), deleted $deletedCount item(s) from target"
} catch {
    $result.success = $false
    $result.message = "Failed to write target file: $_"
}

$result | ConvertTo-Json -Depth 3 | Write-Output
