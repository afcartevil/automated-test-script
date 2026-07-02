# MacroSearch.ps1 - Macro control file search script (optimized)
# Usage: powershell -ExecutionPolicy Bypass -File MacroSearch.ps1 <BasePath> <SearchPattern> [FileTypes]
# Output: JSON list of matched files with line numbers and context
#
# Performance: Automatically excludes non-relevant directories (projects, gradle, build)
# to avoid scanning thousands of unrelated files.

param(
    [Parameter(Mandatory=$true)]
    [string]$BasePath,
    [Parameter(Mandatory=$true)]
    [string]$SearchPattern,
    [string]$FileTypes = ".h,.c,.cpp,.sh,.cfg,.json"
)

if (-not (Test-Path $BasePath)) {
    @{ error = "PATH_NOT_FOUND"; path = $BasePath } | ConvertTo-Json -Compress | Write-Output
    exit 1
}

$basePathTrimmed = $BasePath.TrimEnd('\')
$extList = $FileTypes -split ',' | ForEach-Object { $_.Trim() }

# Directories to exclude (not macro control related)
$excludeDirs = @("projects", "gradle", ".gradle", "build", "out", ".git", ".idea")

# Known files to exclude (handled by lock_nv_skill)
$excludeFiles = @("sml_public_def.h", "l4_nvram_def.h", "l4_nvram_editor.h")

# Function to detect macro type from a line
function Get-MacroType {
    param([string]$line)
    $trimmed = $line.TrimStart()
    if ($trimmed -match '^#\s*ifdef\s') { return "ifdef" }
    if ($trimmed -match '^#\s*ifndef\s') { return "ifndef" }
    if ($trimmed -match '^#\s*elif\s+defined\s*\(') { return "elif_defined" }
    if ($trimmed -match '^#\s*elif\s+') { return "elif" }
    if ($trimmed -match '^#\s*if\s+defined\s*\(') { return "if_defined" }
    if ($trimmed -match '^#\s*if\s+') { return "if" }
    if ($trimmed -match 'defined\s*\(') { return "defined_in_condition" }
    return "other"
}

# Function to capture context around a matching line
function Get-LineContext {
    param(
        [string]$filePath,
        [int]$lineNumber,
        [int]$contextLines = 3
    )

    try {
        $allLines = [System.IO.File]::ReadAllLines($filePath, [System.Text.Encoding]::GetEncoding("GBK"))
    } catch {
        try {
            $allLines = Get-Content -Path $filePath -Encoding UTF8
        } catch {
            return @{ before = @(); after = @(); lineContent = "" }
        }
    }

    $zeroIdx = $lineNumber - 1  # findstr line numbers are 1-based
    $lineContent = ""
    $before = @()
    $after = @()

    if ($zeroIdx -ge 0 -and $zeroIdx -lt $allLines.Count) {
        $lineContent = $allLines[$zeroIdx]
    }

    # Capture context before (up to $contextLines lines)
    $startBefore = [Math]::Max(0, $zeroIdx - $contextLines)
    for ($i = $startBefore; $i -lt $zeroIdx; $i++) {
        if ($i -ge 0 -and $i -lt $allLines.Count) {
            $before += $allLines[$i]
        }
    }

    # Capture context after (up to $contextLines lines)
    $endAfter = [Math]::Min($allLines.Count - 1, $zeroIdx + $contextLines)
    for ($i = $zeroIdx + 1; $i -le $endAfter; $i++) {
        if ($i -ge 0 -and $i -lt $allLines.Count) {
            $after += $allLines[$i]
        }
    }

    return @{ before = $before; after = $after; lineContent = $lineContent }
}

# Phase 1: Collect search directories
$searchDirs = @()
$topLevelDirs = Get-ChildItem -Path $BasePath -Directory -ErrorAction SilentlyContinue

foreach ($dir in $topLevelDirs) {
    if ($excludeDirs -notcontains $dir.Name) {
        $searchDirs += $dir.FullName
    }
}

if ($searchDirs.Count -eq 0) {
    $searchDirs = @($BasePath)
}

# Phase 2: Run findstr /n on each relevant subdirectory to get line numbers
$filePatterns = $extList | ForEach-Object { "*$_" }

$matchedResults = @()

foreach ($searchDir in $searchDirs) {
    # Build findstr command for this directory - use /n for line numbers
    $findstrFiles = ($filePatterns | ForEach-Object { "`"$searchDir\$_`"" }) -join ' '
    $cmdLine = "/c findstr /s /n /c:`"$SearchPattern`" $findstrFiles"
    $rawOutput = cmd.exe $cmdLine 2>$null

    if (-not $rawOutput) { continue }

    $rawResults = @($rawOutput) | Where-Object { $_ -and $_.Trim() }

    foreach ($line in $rawResults) {
        $line = $line.Trim()
        # findstr /n output format: <fullPath>:<lineNumber>:<matchedText>
        # e.g. Z:\path\file.h:89:content
        # Windows paths have colons in drive letter (Z:), so we need to parse from the end
        # The lineNumber is always a number, so find the pattern :<digits>: in the string
        if ($line -notmatch '^(.+):(\d+):(.*)$') { continue }
        $filePath = $Matches[1]
        $lineNumber = [int]$Matches[2]
        $lineContent = $Matches[3]

        $fileName = [System.IO.Path]::GetFileName($filePath)

        # Skip excluded files
        if ($excludeFiles -contains $fileName) { continue }

        $relativePath = $filePath.Replace($basePathTrimmed + '\', '')
        $fileExt = [System.IO.Path]::GetExtension($filePath)
        $macroType = Get-MacroType -line $lineContent
        $context = Get-LineContext -filePath $filePath -lineNumber $lineNumber

        $matchedResults += @{
            fullPath = $filePath
            relativePath = $relativePath
            fileName = $fileName
            fileType = $fileExt
            lineNumber = $lineNumber
            lineContent = $lineContent
            macroType = $macroType
            contextBefore = $context.before
            contextAfter = $context.after
        }
    }
}

# Group results by file for cleaner output
$fileGroups = @{}
foreach ($match in $matchedResults) {
    $rp = $match.relativePath
    if (-not $fileGroups.ContainsKey($rp)) {
        $fileGroups[$rp] = @{
            fullPath = $match.fullPath
            relativePath = $rp
            fileName = $match.fileName
            fileType = $match.fileType
            matches = @()
        }
    }
    $fileGroups[$rp].matches += @{
        lineNumber = $match.lineNumber
        lineContent = $match.lineContent
        macroType = $match.macroType
        contextBefore = $match.contextBefore
        contextAfter = $match.contextAfter
    }
}

$filesOutput = @($fileGroups.Values)

$result = @{
    basePath = $BasePath
    searchPattern = $SearchPattern
    matchedCount = $fileGroups.Count
    files = $filesOutput
}

$result | ConvertTo-Json -Depth 5 | Write-Output
