#Requires -Version 5.1
<#
.SYNOPSIS
  DOU JIRA 前置：读单、下载高功耗日志到 SMB、匹配低功耗目录、解压、MTK 时间转换。
.PARAMETER JiraKey
  JIRA 单号，如 X6879OS161-3796
.PARAMETER SkipDownload
  跳过下载（仅解析已有 high + 匹配 low + 解压/转换）
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$JiraKey,
    [switch]$SkipDownload
)

$ErrorActionPreference = 'Stop'

chcp 65001 | Out-Null
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new()
$env:PYTHONUTF8 = '1'

$SmbHighRoot = '\\10.205.4.20\sw_temp\底软通信开发部\lzx\DOU高功耗文件夹'
$SmbLowRoot  = '\\10.205.4.20\sw_temp\底软通信开发部\lzx\DOUtestPASS数据'
$SkillHub    = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..\..\..\..')).Path
$JiraScript  = Join-Path $SkillHub 'analysis\base\jirainfo\scripts\jira_info.py'
$DownloadScript = Join-Path $SkillHub 'analysis\base\download\scripts\download.py'
$TimeConvertScript = Join-Path $SkillHub 'analysis\base\mtk_kernellog_convert\scripts\time_convert.py'

function Test-DouDataDir([string]$Dir) {
    if (-not (Test-Path $Dir)) { return $false }
    if (Get-ChildItem -Path $Dir -Recurse -File -Filter 'testReport.xlsx' -ErrorAction SilentlyContinue | Select-Object -First 1) {
        return $true
    }
    $meta = Join-Path $Dir 'meta_report'
    if (Test-Path $meta) {
        $any = Get-ChildItem -Path $meta -File -Filter '*.xlsx' -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -notmatch 'DOU3\.0|对比|~\$' } | Select-Object -First 1
        if ($any) { return $true }
    }
    $fallback = Get-ChildItem -Path $Dir -Recurse -File -Filter '*.xlsx' -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -notmatch 'DOU3\.0|对比|~\$' } | Select-Object -First 1
    return [bool]$fallback
}

function Get-DouDataDirs([string]$Root, [int]$MaxDepth = 6) {
    if (-not (Test-Path $Root)) { return @() }
    $found = @()
    $queue = @(@{ Path = $Root; Depth = 0 })
    while ($queue.Count -gt 0) {
        $item = $queue[0]
        $queue = $queue[1..($queue.Count - 1)]
        if ($item.Depth -gt $MaxDepth) { continue }
        try {
            Get-ChildItem -LiteralPath $item.Path -Directory -ErrorAction Stop | ForEach-Object {
                if (Test-DouDataDir $_.FullName) {
                    $script:found += $_.FullName
                }
                if ($item.Depth -lt $MaxDepth) {
                    $queue += @{ Path = $_.FullName; Depth = $item.Depth + 1 }
                }
            }
        } catch { }
    }
    return $found | Select-Object -Unique
}

function Get-CompareHints([string]$Summary, [string]$Description) {
    $text = "$Summary`n$Description"
    $project = $null
    if ($text -match '【[^】]*】[^【]*【(X\d+[A-Z0-9]*)】') { $project = $Matches[1] }
    elseif ($text -match '\b(X\d+[A-Z0-9]{2,})\b') { $project = $Matches[1] }
    $compareOs = $null
    if ($text -match '对比\s*tOS\s*([\d.]+)') { $compareOs = $Matches[1] }
    elseif ($text -match '对比\s*([\d.]+)\s*功耗') { $compareOs = $Matches[1] }
    $highOs = $null
    if ($text -match '【([\d.]+)\s*收编】') { $highOs = $Matches[1] }
    elseif ($text -match 'tOS\s*([\d.]+)\s*收编') { $highOs = $Matches[1] }
    $sn = $null
    if ($text -match 'SN(\d{10,}[A-Z0-9]*)') { $sn = $Matches[1] }
    elseif ($text -match 'CC(\d{12,})') { $sn = "CC$($Matches[1])" }
    return @{ project = $project; compareOs = $compareOs; highOs = $highOs; sn = $sn; text = $text }
}

function Score-LowCandidate([string]$Path, $Hints, [string]$HighPath) {
    $score = 0
    $name = Split-Path $Path -Leaf
    $full = $Path
    if ($HighPath -and ($full -eq $HighPath -or $full.StartsWith($HighPath))) { return -1000 }
    if (Test-Path (Join-Path $Path 'phone_logs\mobile_log*.zip')) { $score += 8 }
    elseif (Get-ChildItem -Path (Join-Path $Path 'phone_logs') -Filter 'mobile_log*' -Directory -ErrorAction SilentlyContinue | Select-Object -First 1) {
        $score += 6
    }
    if ($Hints.project -and ($full -match [regex]::Escape($Hints.project))) { $score += 12 }
    if ($Hints.compareOs -and ($name -match [regex]::Escape($Hints.compareOs) -or $full -match "tOS$([regex]::Escape($Hints.compareOs))")) { $score += 15 }
    if ($Hints.sn -and ($name -match [regex]::Escape($Hints.sn) -or $full -match [regex]::Escape($Hints.sn))) { $score += 8 }
    if ($name -match 'PowerMonitor|PASS|pass') { $score += 5 }
    if ($Hints.highOs -and ($name -match [regex]::Escape($Hints.highOs) -or $full -match "tOS$([regex]::Escape($Hints.highOs))")) { $score -= 10 }
    if ($name -match 'dou3') { $score += 2 }
    return $score
}

function Expand-DouZipIfNeeded([string]$ZipPath) {
    if (-not (Test-Path -LiteralPath $ZipPath)) { return $null }
    $dir = Split-Path -LiteralPath $ZipPath -Parent
    $base = [System.IO.Path]::GetFileNameWithoutExtension($ZipPath)
    $out = Join-Path $dir $base
    if (-not (Test-Path -LiteralPath $out)) {
        Expand-Archive -LiteralPath $ZipPath -DestinationPath $out -Force
    }
    return $out
}

function Invoke-DouUnzipAndConvert([string]$Dir) {
    $result = @{ unzipped = @(); bugreport_unzipped = @(); linli_count = 0; time_converted = $false }
    $zip = Get-ChildItem -Path (Join-Path $Dir 'phone_logs') -File -Filter 'mobile_log*.zip' -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($zip) {
        $out = Expand-DouZipIfNeeded $zip.FullName
        if ($out) { $result.unzipped += $out }
    }
    Get-ChildItem -Path (Join-Path $Dir 'phone_logs') -Recurse -File -Filter 'bugreport*.zip' -ErrorAction SilentlyContinue |
        ForEach-Object {
            $out = Expand-DouZipIfNeeded $_.FullName
            if ($out) { $result.bugreport_unzipped += $out }
        }
    $result.linli_count = @(Get-ChildItem -LiteralPath $Dir -Recurse -File -Filter '*_linli_666.txt' -ErrorAction SilentlyContinue).Count
    if ($result.linli_count -eq 0) {
        $hasRaw = @(Get-ChildItem -LiteralPath $Dir -Recurse -File -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -like 'kernel_log_*' -or $_.Name -like 'events_log_*' } |
            Where-Object { $_.Name -notlike '*_linli_666.txt' }).Count -gt 0
        if ($hasRaw) {
            & python $TimeConvertScript $Dir
            if ($LASTEXITCODE -ne 0) { throw "time_convert 失败: $Dir" }
            $result.time_converted = $true
            $result.linli_count = @(Get-ChildItem -LiteralPath $Dir -Recurse -File -Filter '*_linli_666.txt' -ErrorAction SilentlyContinue).Count
        }
    }
    return $result
}

# --- 1) 读 JIRA ---
if (-not (Test-Path $JiraScript)) { throw "未找到 jira_info.py: $JiraScript" }
$jiraJson = & python $JiraScript -i $JiraKey -f summary -f description 2>&1
if ($LASTEXITCODE -ne 0) { throw "读取 JIRA 失败: $jiraJson" }
$issue = $jiraJson | ConvertFrom-Json
$summary = [string]$issue.summary
$description = [string]$issue.description
$hints = Get-CompareHints $summary $description
Write-Host "JIRA: $JiraKey"
Write-Host "summary: $summary"

# --- 2) 高功耗目录：SMB 已有则跳过下载 ---
$high = $null
$highSource = $null
$existing = Get-DouDataDirs $SmbHighRoot 4 | Sort-Object { $_ } -Descending
if ($existing.Count -gt 0) {
    $ranked = $existing | ForEach-Object {
        $s = 0
        if ($hints.sn -and ($_ -match [regex]::Escape($hints.sn))) { $s += 20 }
        if ($hints.project -and ($_ -match [regex]::Escape($hints.project))) { $s += 10 }
        if ($hints.highOs -and ($_ -match [regex]::Escape($hints.highOs))) { $s += 8 }
        if ($_ -match 'dou3') { $s += 5 }
        [pscustomobject]@{ Path = $_; Score = $s }
    } | Sort-Object Score -Descending
    $best = $ranked | Select-Object -First 1
    if ($best.Score -ge 5) {
        $high = $best.Path
        $highSource = 'smb_high_existing'
    }
}

if (-not $high -and -not $SkipDownload) {
    if (-not (Test-Path $DownloadScript)) { throw "未找到 download.py: $DownloadScript" }
    if (-not (Test-Path $SmbHighRoot)) { New-Item -ItemType Directory -Path $SmbHighRoot -Force | Out-Null }
    Write-Host "下载到: $SmbHighRoot"
    $dlText = "JIRA $JiraKey`n$description"
    & python $DownloadScript $dlText $SmbHighRoot
    if ($LASTEXITCODE -ne 0) { throw "download.py 失败 (code=$LASTEXITCODE)" }
    if (-not (Test-Path (Join-Path $SmbHighRoot 'downloadresult.txt'))) {
        Write-Warning '未找到 downloadresult.txt，继续扫描目录'
    }
    $after = Get-DouDataDirs $SmbHighRoot 6 | Sort-Object { $_ } -Descending
    if ($after.Count -eq 0) { throw "下载后未找到含 testReport.xlsx 的目录，请检查 JIRA 链接或手动放入 $SmbHighRoot" }
    $high = ($after | Select-Object -First 1)
    $highSource = 'smb_high_downloaded'
}

if (-not $high) {
    throw "无法确定高功耗目录。请确认 $SmbHighRoot 下已有完整 DOU 目录，或去掉 -SkipDownload 重新下载。"
}

# --- 3) 低功耗目录：在 DOUtestPASS数据 下自动匹配 ---
$lowCandidates = Get-DouDataDirs $SmbLowRoot 8
$lowRanked = $lowCandidates | ForEach-Object {
    [pscustomobject]@{ Path = $_; Score = (Score-LowCandidate $_ $hints $high) }
} | Where-Object { $_.Score -gt 0 } | Sort-Object Score -Descending

$low = $null
$lowSource = $null
if ($lowRanked.Count -gt 0) {
    $low = $lowRanked[0].Path
    $lowSource = 'smb_low_match'
}

if (-not $low) {
    throw "在 $SmbLowRoot 下未匹配到低功耗目录。候选数=$($lowCandidates.Count)。请检查 summary 中的对比版本/项目名，或手动指定 low 路径。"
}

Write-Host "high ($highSource): $high"
Write-Host "low  ($lowSource): $low"
if ($lowRanked.Count -gt 1) {
    Write-Host 'low 备选:'
    $lowRanked | Select-Object -First 5 | ForEach-Object { Write-Host "  [$($_.Score)] $($_.Path)" }
}

# --- 4) 解压 + 时间转换 ---
$prepHigh = Invoke-DouUnzipAndConvert $high
$prepLow  = Invoke-DouUnzipAndConvert $low
Write-Host "prepare high: linli=$($prepHigh.linli_count) converted=$($prepHigh.time_converted)"
Write-Host "prepare low:  linli=$($prepLow.linli_count) converted=$($prepLow.time_converted)"

# --- 5) 落盘 dou_prepare_result.json（在高功耗目录） ---
$out = @{
    success = $true
    jira_key = $JiraKey
    jira_summary = $summary
    high = $high
    low = $low
    smb_high_root = $SmbHighRoot
    smb_low_root = $SmbLowRoot
    path_resolve = @{
        high = @{ success = $true; high = $high; source = $highSource }
        low  = @{ success = $true; low = $low; source = $lowSource; candidates = @($lowRanked.Path) }
    }
    hints = $hints
    prepare = @{
        high = $prepHigh
        low  = $prepLow
    }
}
$outPath = Join-Path $high 'dou_prepare_result.json'
$out | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $outPath -Encoding UTF8
Write-Host "已输出: $outPath"

# 供后续脚本读取
Write-Output "HIGH=$high"
Write-Output "LOW=$low"
