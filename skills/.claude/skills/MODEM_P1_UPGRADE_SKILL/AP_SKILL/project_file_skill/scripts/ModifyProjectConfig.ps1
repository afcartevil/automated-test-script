# ModifyProjectConfig.ps1 - Update CUSTOM_MODEM macro in AP project file
# Usage: powershell -ExecutionPolicy Bypass -File ModifyProjectConfig.ps1 `
#   -BOM_Name_Target "<new BOM name>" `
#   -AP_Project_Path "<AP project path>"

param(
    [Parameter(Mandatory=$true)]
    [string]$BOM_Name_Target,

    [Parameter(Mandatory=$true)]
    [string]$AP_Project_Path
)

if (-not (Test-Path $AP_Project_Path)) {
    @{ success = $false; error = "AP project path does not exist: $AP_Project_Path" } | ConvertTo-Json -Compress | Write-Output
    exit 1
}

# Find ProjectConfig.mk — support both path formats:
#   1. AP_Project_Path = full target folder (contains ProjectConfig.mk directly)
#   2. AP_Project_Path = parent directory (need to find BOM_Name_Target subfolder)
$configFile = $null

# Try direct path first
$directPath = Join-Path -Path $AP_Project_Path -ChildPath "ProjectConfig.mk"
if (Test-Path $directPath) {
    $configFile = $directPath
} else {
    # Try subfolder
    $targetFolder = Join-Path -Path $AP_Project_Path -ChildPath $BOM_Name_Target
    if (Test-Path $targetFolder) {
        $configFile = Join-Path -Path $targetFolder -ChildPath "ProjectConfig.mk"
    }
}

if (-not $configFile -or -not (Test-Path $configFile)) {
    @{ success = $false; error = "ProjectConfig.mk not found. Tried: $directPath and $(Join-Path (Join-Path $AP_Project_Path $BOM_Name_Target) 'ProjectConfig.mk')" } | ConvertTo-Json -Compress | Write-Output
    exit 1
}

# Read file content
try {
    $content = [System.IO.File]::ReadAllText($configFile, [System.Text.Encoding]::UTF8)
} catch {
    @{ success = $false; error = "Failed to read file: $_" } | ConvertTo-Json -Compress | Write-Output
    exit 1
}

# Find CUSTOM_MODEM macro
$pattern = '(CUSTOM_MODEM\s*=\s*)[^#\r\n]*'
$match = [regex]::Match($content, $pattern)
if (-not $match.Success) {
    @{ success = $false; error = "CUSTOM_MODEM macro not found in $configFile" } | ConvertTo-Json -Compress | Write-Output
    exit 1
}

$originalValue = $match.Value.Trim()
$prefix = $match.Groups[1].Value

if ($originalValue -eq "CUSTOM_MODEM = $BOM_Name_Target") {
    @{
        success = $true
        message = "CUSTOM_MODEM already set to $BOM_Name_Target"
        modified_file = $configFile
        original_value = $originalValue
        new_value = $originalValue
        changed = $false
    } | ConvertTo-Json -Compress | Write-Output
    exit 0
}

# Backup
$backupFile = "$configFile.backup_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
Copy-Item -Path $configFile -Destination $backupFile -Force

# Replace
$newValue = "${prefix}$BOM_Name_Target"
$newContent = $content.Replace($originalValue, $newValue)

try {
    [System.IO.File]::WriteAllText($configFile, $newContent, [System.Text.Encoding]::UTF8)
} catch {
    @{ success = $false; error = "Failed to write file: $_" } | ConvertTo-Json -Compress | Write-Output
    exit 1
}

@{
    success = $true
    message = "CUSTOM_MODEM updated from '$originalValue' to '$BOM_Name_Target'"
    modified_file = $configFile
    original_value = $originalValue
    new_value = "CUSTOM_MODEM = $BOM_Name_Target"
    changed = $true
} | ConvertTo-Json -Compress | Write-Output
