# GpioCheckModify.ps1 - GPIO configuration diff check and auto-apply
# Usage: powershell -ExecutionPolicy Bypass -File GpioCheckModify.ps1 `
#   -BOM_Name_Target "<new BOM name>" `
#   -Path_C "<source .dws path>" `
#   -Path_D "<target .dws path>" `
#   -Is_TOS16_Before <true|false> `
#   [-AutoApply]
#
# If -AutoApply is set, differences are automatically applied without prompting.
# Without -AutoApply, only diff report is output.

param(
    [Parameter(Mandatory=$true)]
    [string]$BOM_Name_Target,

    [Parameter(Mandatory=$true)]
    [string]$Path_C,

    [Parameter(Mandatory=$true)]
    [string]$Path_D,

    [Parameter(Mandatory=$true)]
    [string]$Is_TOS16_Before,

    [switch]$AutoApply
)

$result = @{
    success = $false
    message = ""
    differences = @()
    modified_count = 0
    drdi_result = $null
}

# --- Helper: Read file with encoding fallback ---
function Read-File {
    param([string]$path)
    try {
        return [System.IO.File]::ReadAllText($path, [System.Text.Encoding]::GetEncoding("UTF8"))
    } catch {
        try {
            return Get-Content -Path $path -Raw
        } catch {
            return $null
        }
    }
}

function Write-File {
    param([string]$path, [string]$content)
    try {
        [System.IO.File]::WriteAllText($path, $content, [System.Text.Encoding]::GetEncoding("UTF8"))
        return $true
    } catch {
        return $false
    }
}

# ============================================================
# STEP 1: Locate .dws files
# ============================================================
$dwsFiles_C = Get-ChildItem -Path $Path_C -Filter "*.dws" -Recurse -ErrorAction SilentlyContinue
$targetDwsFile_C = $dwsFiles_C | Where-Object { $_.Name -match [regex]::Escape($BOM_Name_Target) } | Select-Object -First 1

if (-not $targetDwsFile_C) {
    $result.message = "No .dws file found for $BOM_Name_Target in Path_C: $Path_C"
    $result | ConvertTo-Json -Depth 3 | Write-Output
    exit 1
}

$dwsFiles_D = Get-ChildItem -Path $Path_D -Filter "*.dws" -Recurse -ErrorAction SilentlyContinue
$targetDwsFile_D = $dwsFiles_D | Where-Object { $_.Name -match [regex]::Escape($BOM_Name_Target) } | Select-Object -First 1

if (-not $targetDwsFile_D) {
    $result.message = "No .dws file found for $BOM_Name_Target in Path_D: $Path_D"
    $result | ConvertTo-Json -Depth 3 | Write-Output
    exit 1
}

# ============================================================
# STEP 2: Locate .fig file and extract GPIO numbers
# ============================================================
$platformPattern = "mt\d+"
$match = [regex]::Match($Path_D, $platformPattern)
if (-not $match.Success) {
    $match = [regex]::Match($Path_C, $platformPattern)
}
if (-not $match.Success) {
    $result.message = "Cannot extract platform number from paths"
    $result | ConvertTo-Json -Depth 3 | Write-Output
    exit 1
}

$platform = $match.Value
$figFileName = "$platform.fig"

# Smart .fig file search: walk up from path to find tools/dct, plus hardcoded fallbacks
function Find-FigFile {
    param([string]$basePath, [string]$platform)
    # Walk up from base path, look in tools\dct for any .fig matching platform (case-insensitive)
    $current = $basePath
    $maxDepth = 15
    $depth = 0
    while ($depth -lt $maxDepth -and $current -and (Split-Path $current -Parent) -ne $current) {
        $dctPath = Join-Path $current "tools\dct"
        if (Test-Path $dctPath) {
            $figFile = Get-ChildItem -Path $dctPath -Filter "$platform.fig" -ErrorAction SilentlyContinue | Select-Object -First 1
            if (-not $figFile) {
                # Try case-insensitive search
                $figFile = Get-ChildItem -Path $dctPath -ErrorAction SilentlyContinue | Where-Object { $_.Name -imatch "^${platform}\.fig$" } | Select-Object -First 1
            }
            if ($figFile) { return $figFile.FullName }
        }
        $current = Split-Path $current -Parent
        $depth++
    }
    return $null
}

$figPath = $null
# Search from both paths
$figPath = Find-FigFile -basePath $Path_C -platform $platform
if (-not $figPath) {
    $figPath = Find-FigFile -basePath $Path_D -platform $platform
}
# Hardcoded fallbacks (case-insensitive)
if (-not $figPath) {
    $fallbackDirs = @(
        "Z:\S-AP\vendor\mediatek\proprietary\tools\dct",
        "Z:\W-AP\vendor\mediatek\proprietary\tools\dct",
        "Z:\S-od\vendor\mediatek\proprietary\tools\dct",
        "Z:\W-od\vendor\mediatek\proprietary\tools\dct"
    )
    foreach ($dir in $fallbackDirs) {
        if (Test-Path $dir) {
            $figFile = Get-ChildItem -Path $dir -ErrorAction SilentlyContinue | Where-Object { $_.Name -imatch "^${platform}\.fig$" } | Select-Object -First 1
            if ($figFile) { $figPath = $figFile.FullName; break }
        }
    }
}

if (-not $figPath) {
    $result.message = ".fig file not found for platform $platform (searched tools\dct directories walking up from Path_C/Path_D and vendor fallbacks)"
    $result | ConvertTo-Json -Depth 3 | Write-Output
    exit 1
}

$figContent = Get-Content -Path $figPath -Raw

# Extract GPIO numbers from .fig file
function Extract-GpioFromFig {
    param([string]$figContent, [string]$pattern)
    $matches = [regex]::Matches($figContent, $pattern)
    return ($matches | ForEach-Object { $_.Groups[1].Value } | Select-Object -Unique | Sort-Object { [int]$_ })
}

$bpiGpios = Extract-GpioFromFig -figContent $figContent -pattern 'GPIO(\d+).*MODE1\(BPI_BUS'
$mipiGpios = Extract-GpioFromFig -figContent $figContent -pattern 'GPIO(\d+).*MODE1\(MIPI'
$hotplugGpios = Extract-GpioFromFig -figContent $figContent -pattern 'GPIO(\d+).*HOT_PLUG'

# ============================================================
# STEP 3: Read .dws files
# ============================================================
$dwsContent_C = Read-File -path $targetDwsFile_C.FullName
$dwsContent_D = Read-File -path $targetDwsFile_D.FullName

if ($null -eq $dwsContent_C -or $null -eq $dwsContent_D) {
    $result.message = "Failed to read .dws files"
    $result | ConvertTo-Json -Depth 3 | Write-Output
    exit 1
}

# ============================================================
# STEP 4: Extract SIM GPIOs from .dws file
# ============================================================
$simPattern = '<varName0>GPIO_SIM\d+_(SCLK|SRST|SIO)</varName0>'
$simMatches_C = [regex]::Matches($dwsContent_C, $simPattern)
$simGpios_C = @()
foreach ($m in $simMatches_C) {
    # Find the gpio tag before this varName0
    $idx = $m.Index
    $beforeText = $dwsContent_C.Substring(0, $idx)
    $lastGpio = [regex]::Match($beforeText, '<gpio(\d+)>[^<]*$')
    if ($lastGpio.Success) {
        $simGpios_C += $lastGpio.Groups[1].Value
    }
}
$simGpios_C = $simGpios_C | Select-Object -Unique | Sort-Object { [int]$_ }

# ============================================================
# STEP 5: Compare GPIO configurations
# ============================================================
function Get-GpioConfig {
    param([string]$content, [string]$gpioNum)
    $pattern = "<gpio$gpioNum>([\s\S]*?)</gpio$gpioNum>"
    $match = [regex]::Match($content, $pattern)
    if ($match.Success) {
        # Exclude <smt> and <ies> from comparison - they are platform-specific and not functional differences
        $block = $match.Groups[1].Value -replace '\s+', ' ' | ForEach-Object { $_.Trim() }
        $block = $block -replace '<smt>.*?</smt>', '' -replace '<ies>.*?</ies>', '' -replace '\s+', ' '
        return $block.Trim()
    }
    return "not_configured"
}

function Compare-Gpio {
    param([string]$gpioNum, [string]$contentC, [string]$contentD, [string]$category)
    $configC = Get-GpioConfig -content $contentC -gpioNum $gpioNum
    $configD = Get-GpioConfig -content $contentD -gpioNum $gpioNum
    $isDiff = ($configC -ne $configD)
    return [pscustomobject]@{
        gpioNum = $gpioNum
        category = $category
        configC = $configC
        configD = $configD
        hasDiff = $isDiff
    }
}

$differences = @()

# Extract SIM GPIOs from target file as well (union of both sides)
$simMatches_D = [regex]::Matches($dwsContent_D, $simPattern)
$simGpios_D = @()
foreach ($m in $simMatches_D) {
    $idx = $m.Index
    $beforeText = $dwsContent_D.Substring(0, $idx)
    $lastGpio = [regex]::Match($beforeText, '<gpio(\d+)>[^<]*$')
    if ($lastGpio.Success) {
        $simGpios_D += $lastGpio.Groups[1].Value
    }
}
$simGpios_D = $simGpios_D | Select-Object -Unique | Sort-Object { [int]$_ }

# Use union of source and target GPIOs for each category
$allSimGpios = @($simGpios_C + $simGpios_D | Select-Object -Unique | Sort-Object { [int]$_ })

function Add-Comparisons {
    param([string[]]$gpios, [string]$category)
    $localDiffs = @()
    foreach ($gpio in $gpios) {
        $r = Compare-Gpio -gpioNum $gpio -contentC $dwsContent_C -contentD $dwsContent_D -category $category
        if ($r.hasDiff) {
            $localDiffs += $r
        }
    }
    return $localDiffs
}

$differences = @()
$differences += Add-Comparisons -gpios $allSimGpios -category "SIM"
$differences += Add-Comparisons -gpios $hotplugGpios -category "HOT_PLUG"
$differences += Add-Comparisons -gpios $bpiGpios -category "BPI"
$differences += Add-Comparisons -gpios $mipiGpios -category "MIPI"
$differences = @($differences)

# ============================================================
# STEP 5b: Compare md1_eint module (SIM/MD1 EINT config)
# ============================================================
function Get-ModuleContent {
    param([string]$content, [string]$moduleName)
    $pattern = "(<module name=`"$moduleName`">[\s\S]*?</module>)"
    $match = [regex]::Match($content, $pattern)
    if ($match.Success) {
        return $match.Groups[1].Value -replace '\s+', ' ' | ForEach-Object { $_.Trim() }
    }
    return $null
}

$md1eint_C = Get-ModuleContent -content $dwsContent_C -moduleName "md1_eint"
$md1eint_D = Get-ModuleContent -content $dwsContent_D -moduleName "md1_eint"

if ($md1eint_C -ne $null -or $md1eint_D -ne $null) {
    if ($md1eint_C -ne $md1eint_D) {
        $differences += [pscustomobject]@{
            gpioNum = "md1_eint"
            category = "MD1_EINT"
            configC = if ($md1eint_C) { $md1eint_C } else { "not_configured" }
            configD = if ($md1eint_D) { $md1eint_D } else { "not_configured" }
            hasDiff = $true
        }
    }
}

$differences = @($differences)

# ============================================================
# STEP 6: DRDI check (ADC configuration)
# ============================================================
# Run DRDI check regardless of GPIO differences - it always needs to report status
$drdiResult = @{ found = $false; adc_num_C = $null; adc_num_D = $null; status = "not_found" }

$adcMatch_C = [regex]::Match($dwsContent_C, '<varName>ADC_FDD_RF_PARAMS_DYNAMIC_CUSTOM_CH</varName>')
$adcMatch_D = [regex]::Match($dwsContent_D, '<varName>ADC_FDD_RF_PARAMS_DYNAMIC_CUSTOM_CH</varName>')

if ($adcMatch_C.Success -and $adcMatch_D.Success) {
    # Both have ADC config, check if ADC number matches
    $adcBlocks_C = [regex]::Matches($dwsContent_C, '<adc(\d+)>([\s\S]*?)</adc\1>')
    foreach ($block in $adcBlocks_C) {
        if ($block.Groups[2].Value -match 'ADC_FDD_RF_PARAMS_DYNAMIC_CUSTOM_CH') {
            $drdiResult.adc_num_C = "adc$($block.Groups[1].Value)"
            break
        }
    }
    $adcBlocks_D = [regex]::Matches($dwsContent_D, '<adc(\d+)>([\s\S]*?)</adc\1>')
    foreach ($blockD in $adcBlocks_D) {
        if ($blockD.Groups[2].Value -match 'ADC_FDD_RF_PARAMS_DYNAMIC_CUSTOM_CH') {
            $drdiResult.adc_num_D = "adc$($blockD.Groups[1].Value)"
            break
        }
    }
    $drdiResult.found = $true
    if ($drdiResult.adc_num_C -ne $drdiResult.adc_num_D) {
        $drdiResult.status = "mismatch"
    } else {
        $drdiResult.status = "consistent"
    }
} elseif ($adcMatch_C.Success -and -not $adcMatch_D.Success) {
    $drdiResult.found = $true
    $drdiResult.status = "source_has_target_missing"
    $adcBlocks_C = [regex]::Matches($dwsContent_C, '<adc(\d+)>([\s\S]*?)</adc\1>')
    foreach ($block in $adcBlocks_C) {
        if ($block.Groups[2].Value -match 'ADC_FDD_RF_PARAMS_DYNAMIC_CUSTOM_CH') {
            $drdiResult.adc_num_C = "adc$($block.Groups[1].Value)"
            break
        }
    }
} elseif (-not $adcMatch_C.Success -and $adcMatch_D.Success) {
    # Source doesn't have ADC config but target does - this is a difference
    $drdiResult.found = $true
    $drdiResult.status = "target_has_source_missing"
    $adcBlocks_D = [regex]::Matches($dwsContent_D, '<adc(\d+)>([\s\S]*?)</adc\1>')
    foreach ($blockD in $adcBlocks_D) {
        if ($blockD.Groups[2].Value -match 'ADC_FDD_RF_PARAMS_DYNAMIC_CUSTOM_CH') {
            $drdiResult.adc_num_D = "adc$($blockD.Groups[1].Value)"
            break
        }
    }
} else {
    # Neither has ADC config - check DTS as fallback
    $searchPath = Split-Path $Path_C -Parent
    if ($Path_C.Contains("tran_projects")) {
        $dtsFiles = Get-ChildItem -Path $searchPath -Filter "*.dts" -Recurse -ErrorAction SilentlyContinue
        foreach ($dtsFile in $dtsFiles) {
            $dtsContent = Get-Content -Path $dtsFile.FullName -Raw -ErrorAction SilentlyContinue
            if ($dtsContent -match 'md_auxadc' -and $dtsContent -match 'AUXADC_VIN1') {
                $drdiResult.found = $true
                $drdiResult.status = "found_in_dts"
                break
            }
        }
    }
    if (-not $drdiResult.found) {
        $drdiResult.status = "not_found_contact_rf"
    }
}

$result.drdi_result = $drdiResult

# Check if there are any differences to apply
if ($differences.Count -eq 0) {
    $result.success = $true
    $result.message = "No GPIO configuration differences found"
    $result | ConvertTo-Json -Depth 3 | Write-Output
    exit 0
}

# ============================================================
# STEP 7: Apply differences (if -AutoApply)
# ============================================================
if ($AutoApply) {
    # Create backup
    $backupPath = "$($targetDwsFile_D.FullName).backup_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
    Copy-Item -Path $targetDwsFile_D.FullName -Destination $backupPath -Force

    # Get GPIO list to fix
    $gpioList = ($differences | ForEach-Object { $_.gpioNum }) -join ","

    # Call FixGpioOrder.ps1
    $fixScriptPath = Join-Path $PSScriptRoot "FixGpioOrder.ps1"
    if (Test-Path $fixScriptPath) {
        # Execute and capture output; PS scripts don't set LASTEXITCODE reliably
        $scriptOutput = & $fixScriptPath -SourcePath $targetDwsFile_C.FullName -TargetPath $targetDwsFile_D.FullName -GpioList $gpioList 2>&1
        $scriptOutput | ForEach-Object { Write-Output $_ }

        # Check if target file was actually modified by verifying GPIO presence
        $targetContentAfter = Read-File -path $targetDwsFile_D.FullName
        $allFixed = $true
        foreach ($gpioNum in ($differences | ForEach-Object { $_.gpioNum })) {
            if ($targetContentAfter -notmatch "<gpio$gpioNum>") {
                $allFixed = $false
                break
            }
        }
        if ($allFixed) {
            $result.differences = $differences
            $result.modified_count = $differences.Count
            $result.success = $true
            $result.message = "Applied $($differences.Count) GPIO configuration(s) from source to target"
        } else {
            $result.success = $false
            $result.message = "FixGpioOrder.ps1 execution did not produce expected result"
        }
    } else {
        # Fallback: inline GPIO copy
        $modifiedCount = 0
        foreach ($diff in $differences) {
            $gpioNum = $diff.gpioNum
            $srcPattern = "<gpio$gpioNum>([\s\S]*?)</gpio$gpioNum>"
            $srcMatch = [regex]::Match($dwsContent_C, $srcPattern)
            if ($srcMatch.Success) {
                $newBlock = "<gpio$gpioNum>$($srcMatch.Groups[1].Value)</gpio$gpioNum>"
                # Remove existing in target
                $dwsContent_D = $dwsContent_D -replace "<gpio$gpioNum>[\s\S]*?</gpio$gpioNum>`n?", ""
                # Find insert position
                $allGpios = [regex]::Matches($dwsContent_D, '<gpio(\d+)>')
                $existingNums = $allGpios | ForEach-Object { [int]$_.Groups[1].Value } | Sort-Object
                $insertBefore = $null
                foreach ($n in $existingNums) {
                    if ($n -gt [int]$gpioNum) {
                        $insertBefore = $n
                        break
                    }
                }
                if ($insertBefore) {
                    $dwsContent_D = $dwsContent_D.Replace("<gpio$insertBefore>", "`n$newBlock`n<gpio$insertBefore>")
                } else {
                    $dwsContent_D = $dwsContent_D + "`n" + $newBlock
                }
                $modifiedCount++
            }
        }
        if ($modifiedCount -gt 0) {
            $writeOk = Write-File -path $targetDwsFile_D.FullName -content $dwsContent_D
            if ($writeOk) {
                $result.differences = $differences
                $result.modified_count = $modifiedCount
                $result.success = $true
                $result.message = "Applied $modifiedCount GPIO configuration(s) from source to target (inline)"
            }
        }
    }
} else {
    # Just report, no changes
    $result.success = $true
    $result.differences = $differences
    $result.message = "Found $($differences.Count) GPIO difference(s). Use -AutoApply to apply changes."
}

$result | ConvertTo-Json -Depth 5 | Write-Output
