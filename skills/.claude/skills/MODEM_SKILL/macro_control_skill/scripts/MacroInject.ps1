# MacroInject.ps1 - Inject target BOM name into macro control files
# Usage: powershell -ExecutionPolicy Bypass -File MacroInject.ps1 `
#   -TargetBasePath "<target repo path>" `
#   -SourceBasePath "<source repo path>" `
#   -SourceResultsFile "<path to MacroSearch.ps1 JSON output file>" `
#   -BOM_Name_Target "<new BOM name>"
# Output: JSON result with modification details
#
# Injection strategy (dual-strategy for cross-baseline compatibility):
#   1. Exact match: find old BOM in target -> inject after it (existing behavior)
#   2. Context match: use contextBefore from search to find position in target
#   3. Pattern fallback: match same macro type in target -> inject there

param(
    [Parameter(Mandatory=$true)]
    [string]$TargetBasePath,

    [Parameter(Mandatory=$true)]
    [string]$SourceBasePath,

    [Parameter(Mandatory=$true)]
    [string]$SourceResultsFile,

    [Parameter(Mandatory=$true)]
    [string]$BOM_Name_Target
)

if (-not (Test-Path $TargetBasePath)) {
    @{ success = $false; error = "Target path does not exist: $TargetBasePath" } | ConvertTo-Json -Compress | Write-Output
    exit 1
}

if (-not (Test-Path $SourceResultsFile)) {
    @{ success = $false; error = "Search results file does not exist: $SourceResultsFile" } | ConvertTo-Json -Compress | Write-Output
    exit 1
}

$sourceResults = Get-Content -Path $SourceResultsFile -Raw -Encoding UTF8 | ConvertFrom-Json

# Exclusion rules: files that should NOT be modified by this script
# errc_nvram_def.c: IMEI anti-tamper logic has a separate solution
$exclusionRules = @(
    @{ filePattern = "errc_nvram_def.c"; reason = "IMEI anti-tamper has separate solution" }
)

if ($sourceResults.matchedCount -eq 0) {
    @{
        success = $true
        message = "No files to modify"
        modifiedCount = 0
        skippedCount = 0
        details = @()
    } | ConvertTo-Json -Depth 3 | Write-Output
    exit 0
}

$targetBaseTrimmed = $TargetBasePath.TrimEnd('\')
$sourceBaseTrimmed = $SourceBasePath.TrimEnd('\')
$searchPattern = $sourceResults.searchPattern

$details = @()
$modifiedCount = 0
$skippedCount = 0

function Read-TargetFile {
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

function Write-TargetFile {
    param([string]$path, [string]$content)
    try {
        [System.IO.File]::WriteAllText($path, $content, [System.Text.Encoding]::GetEncoding("GBK"))
        return $true
    } catch {
        return $false
    }
}

function Find-ContextMatch {
    param(
        [string[]]$contentLines,
        [string[]]$contextBefore
    )
    if ($null -eq $contextBefore -or $contextBefore.Count -eq 0) {
        return -1
    }
    $ctxCount = $contextBefore.Count
    $maxIdx = $contentLines.Count - $ctxCount
    if ($maxIdx -lt 0) { return -1 }

    for ($i = 0; $i -le $maxIdx; $i++) {
        $allMatch = $true
        for ($j = 0; $j -lt $ctxCount; $j++) {
            $targetLine = $contentLines[$i + $j].Trim()
            $ctxLine = $contextBefore[$j].Trim()
            if ([string]::IsNullOrWhiteSpace($ctxLine)) { continue }
            if ($targetLine -ne $ctxLine) {
                $allMatch = $false
                break
            }
        }
        if ($allMatch) {
            return $i + $ctxCount - 1
        }
    }
    return -1
}

function Find-PatternMatch {
    param(
        [string[]]$contentLines,
        [string]$macroType,
        [int]$startIndex = 0
    )
    for ($i = $startIndex; $i -lt $contentLines.Count; $i++) {
        $line = $contentLines[$i].TrimStart()
        switch ($macroType) {
            "ifdef" {
                if ($line -match '^#\s*ifdef\s') { return $i }
            }
            "ifndef" {
                if ($line -match '^#\s*ifndef\s') { return $i }
            }
            "elif_defined" {
                if ($line -match '^#\s*elif\s+defined\s*\(') { return $i }
            }
            "if_defined" {
                if ($line -match '^#\s*if\s+defined\s*\(') { return $i }
            }
            "defined_in_condition" {
                if ($line -match 'defined\s*\(') { return $i }
            }
            "if" {
                if ($line -match '^#\s*if\s+') { return $i }
            }
            "elif" {
                if ($line -match '^#\s*elif\s+') { return $i }
            }
            "other" {
                if ($line -match '^#\s*(if|ifdef|ifndef|elif)') { return $i }
            }
        }
    }
    return -1
}

# Main processing
$fileList = @($sourceResults.files)
$fi = 0
while ($fi -lt $fileList.Count) {
    $file = $fileList[$fi]
    $fi++

    $targetPath = Join-Path $targetBaseTrimmed $file.relativePath

    $detail = @{
        sourceFile = $file.fullPath
        targetFile = $targetPath
        relativePath = $file.relativePath
        fileType = $file.fileType
        status = ""
        changes = 0
        strategy = ""
    }

    # Check exclusion rules
    $skipExcluded = $false
    foreach ($rule in $exclusionRules) {
        if ($file.relativePath -match [regex]::Escape($rule.filePattern)) {
            $detail.status = "SKIPPED_EXCLUSION"
            $detail.message = "$($rule.reason)"
            $skippedCount++
            $details += $detail
            $skipExcluded = $true
            break
        }
    }
    if ($skipExcluded) { continue }

    if (-not (Test-Path $targetPath)) {
        $detail.status = "SKIPPED_TARGET_NOT_FOUND"
        $detail.message = "Target file does not exist"
        $skippedCount++
        $details += $detail
        continue
    }

    $content = Read-TargetFile -path $targetPath
    if ($null -eq $content) {
        $detail.status = "SKIPPED_READ_ERROR"
        $detail.message = "Failed to read target file"
        $skippedCount++
        $details += $detail
        continue
    }

    $isScriptFile = ($file.fileType -in ".sh", ".cfg", ".json")

    if ($isScriptFile) {
        $oldBOM = $searchPattern
        $targetBOM = $BOM_Name_Target
    } else {
        $oldBOM = $searchPattern
        $targetBOM = "__${BOM_Name_Target}__"
    }

    $isAlreadyModified = $false
    if ($isScriptFile) {
        $pattern = "\|\|[ \t]$([regex]::Escape($targetBOM))(?=\s|$|[^a-zA-Z0-9_])"
        if ($content -match $pattern) { $isAlreadyModified = $true }
    } else {
        $pattern = "defined\($([regex]::Escape($targetBOM))\)"
        if ($content -match $pattern) { $isAlreadyModified = $true }
    }

    if ($isAlreadyModified) {
        $detail.status = "SKIPPED_ALREADY_MODIFIED"
        $detail.message = "Target file already contains $targetBOM"
        $skippedCount++
        $details += $detail
        continue
    }

    if ($isScriptFile) {
        $newInsert = " || $BOM_Name_Target"
    } else {
        $newInsert = " || defined(__${BOM_Name_Target}__)"
    }

    # STRATEGY 1: Exact old BOM match
    $occurrences = ([regex]::Matches($content, [regex]::Escape($oldBOM))).Count
    if ($occurrences -gt 0) {
        $newContent = $content.Replace($oldBOM, "$oldBOM$newInsert")
        $newOccurrences = ([regex]::Matches($newContent, [regex]::Escape($oldBOM + $newInsert))).Count
        if ($newOccurrences -eq $occurrences) {
            $writeOk = Write-TargetFile -path $targetPath -content $newContent
            if ($writeOk) {
                $detail.status = "MODIFIED"
                $detail.changes = $occurrences
                $detail.strategy = "exact_match"
                $detail.oldPattern = $oldBOM
                $detail.newPattern = "$oldBOM$newInsert"
                $modifiedCount++
            } else {
                $detail.status = "FAILED"
                $detail.message = "Failed to write target file"
                $skippedCount++
            }
        } else {
            $detail.status = "FAILED"
            $detail.message = "Replacement verification failed"
            $skippedCount++
        }
        $details += $detail
        continue
    }

    # STRATEGY 2: Context matching — process ALL matches in the file
    $hasMatches = ($null -ne $file.PSObject.Properties['matches'])
    if ($hasMatches -and $file.matches.Count -gt 0) {
        $contentLines = $content -split "`n" | ForEach-Object { $_.TrimEnd("`r") }
        $fileChanges = 0
        $matchedLines = @()

        foreach ($match in $file.matches) {
            $contextBefore = @()
            if ($null -ne $match.PSObject.Properties['contextBefore']) {
                $contextBefore = @($match.contextBefore)
            }

            if ($contextBefore.Count -gt 0) {
                $matchIdx = Find-ContextMatch -contentLines $contentLines -contextBefore $contextBefore
                if ($matchIdx -ge 0 -and $matchIdx -lt $contentLines.Count) {
                    if ($contentLines[$matchIdx] -notmatch [regex]::Escape($newInsert)) {
                        $contentLines[$matchIdx] = $contentLines[$matchIdx] + $newInsert
                        $fileChanges++
                        $matchedLines += ($matchIdx + 1)
                    }
                }
            }
        }

        if ($fileChanges -gt 0) {
            $newContent = ($contentLines -join "`n")
            $writeOk = Write-TargetFile -path $targetPath -content $newContent
            if ($writeOk) {
                $detail.status = "MODIFIED"
                $detail.changes = $fileChanges
                $detail.strategy = "context_match"
                $detail.matchedLines = $matchedLines
                $detail.injectPattern = $newInsert
                $modifiedCount++
            } else {
                $detail.status = "FAILED"
                $detail.message = "Failed to write target file"
                $skippedCount++
            }
            $details += $detail
            continue
        }
    }

    # STRATEGY 3: Pattern matching fallback — process ALL matches in the file
    if ($hasMatches -and $file.matches.Count -gt 0) {
        $contentLines = $content -split "`n" | ForEach-Object { $_.TrimEnd("`r") }
        $fileChanges = 0
        $matchedLines = @()
        $searchStart = 0

        foreach ($match in $file.matches) {
            $macroType = ""
            if ($null -ne $match.PSObject.Properties['macroType']) {
                $macroType = $match.macroType
            }

            if ($macroType) {
                $patternIdx = Find-PatternMatch -contentLines $contentLines -macroType $macroType -startIndex $searchStart
                if ($patternIdx -ge 0 -and $patternIdx -lt $contentLines.Count) {
                    if ($contentLines[$patternIdx] -notmatch [regex]::Escape($newInsert)) {
                        $contentLines[$patternIdx] = $contentLines[$patternIdx] + $newInsert
                        $fileChanges++
                        $matchedLines += ($patternIdx + 1)
                    }
                    $searchStart = $patternIdx + 1  # continue search from next line
                }
            }
        }

        if ($fileChanges -gt 0) {
            $newContent = ($contentLines -join "`n")
            $writeOk = Write-TargetFile -path $targetPath -content $newContent
            if ($writeOk) {
                $detail.status = "MODIFIED"
                $detail.changes = $fileChanges
                $detail.strategy = "pattern_match"
                $detail.matchedLines = $matchedLines
                $detail.injectPattern = $newInsert
                $modifiedCount++
            } else {
                $detail.status = "FAILED"
                $detail.message = "Failed to write target file"
                $skippedCount++
            }
            $details += $detail
            continue
        }
    }

    # All strategies failed
    $detail.status = "SKIPPED_NO_MATCH"
    if ($hasMatches) {
        $detail.message = "Old BOM not found and no matching context/pattern found in target file"
    } else {
        $detail.message = "Old BOM not found in target file (legacy search format without context)"
    }
    $skippedCount++
    $details += $detail
}

$result = @{
    success = $true
    modifiedCount = $modifiedCount
    skippedCount = $skippedCount
    totalCount = $sourceResults.matchedCount
    details = $details
}

$result | ConvertTo-Json -Depth 5 | Write-Output
