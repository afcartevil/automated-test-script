# RF 参数位置搜索脚本
# 用法: powershell -ExecutionPolicy Bypass -File RfSearch.ps1 <Path_A_Pub> <Path_A_Priv> <BOM_Name>
# 输出: JSON 格式的 RF 参数位置信息

param(
    [Parameter(Mandatory=$true)]
    [string]$Path_A_Pub,
    [Parameter(Mandatory=$true)]
    [string]$Path_A_Priv,
    [Parameter(Mandatory=$true)]
    [string]$BOM_Name
)

function Search-BomFolder {
    param([string]$ProjectsPath, [string]$BOM)

    if (-not (Test-Path $ProjectsPath)) { return $null }

    # 精确匹配 BOM 名称
    $foundDirs = Get-ChildItem -Path $ProjectsPath -Recurse -Directory |
        Where-Object { $_.Name -eq $BOM }

    if ($foundDirs -and $foundDirs.Count -eq 1) {
        return $foundDirs[0].FullName
    } elseif ($foundDirs -and $foundDirs.Count -gt 1) {
        return @{ path = $foundDirs[0].FullName; multiple = $true; count = $foundDirs.Count }
    }
    return $null
}

# 阶段 A：尝试读取 .json 文件
function Find-JsonConfig {
    param([string]$PubPath, [string]$PrivPath, [string]$TargetBOM)

    $searchPaths = @()
    if (Test-Path "$PubPath\projects") { $searchPaths += ,@{ path = "$PubPath\projects"; source = "Pub" } }
    if (Test-Path "$PrivPath\projects") { $searchPaths += ,@{ path = "$PrivPath\projects"; source = "Priv" } }

    foreach ($searchItem in $searchPaths) {
        $jp = $searchItem.path
        $src = $searchItem.source
        $jsonFiles = Get-ChildItem -Path $jp -Filter "*.json" -File -ErrorAction SilentlyContinue
        foreach ($jf in $jsonFiles) {
            try {
                $json = Get-Content -Path $jf.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
                $jsonBOM = $json.bom_name -or $json.project_name -or $json.modem_bom
                if ($jsonBOM -and $jsonBOM -eq $TargetBOM) {
                    return @{
                        found = $true
                        source = "json"
                        search_source = $src
                        file = $jf.FullName
                        project_name = $json.project_name
                        rf_param_path = $json.rf_param_path
                        rf_version = $json.rf_param_version
                        config_id = $json.config_id
                        bom_name = $json.bom_name
                    }
                }
            } catch {
                continue
            }
        }
    }
    return @{ found = $false; source = "json" }
}

# ── 执行搜索 ──

$jsonResult = Find-JsonConfig -PubPath $Path_A_Pub -PrivPath $Path_A_Priv -TargetBOM $BOM_Name

if ($jsonResult.found) {
    $jsonResult | ConvertTo-Json | Write-Output
    exit 0
}

# JSON 未找到，执行 grep 搜索（内联实现，避免函数调用问题）
$grepSearchPaths = @()
if (Test-Path "$Path_A_Pub\projects") { $grepSearchPaths += ,@{ path = "$Path_A_Pub\projects"; source = "Pub" } }
if (Test-Path "$Path_A_Priv\projects") { $grepSearchPaths += ,@{ path = "$Path_A_Priv\projects"; source = "Priv" } }

$grepFound = $null
$grepSource = ""

foreach ($gp in $grepSearchPaths) {
    $found = Search-BomFolder -ProjectsPath $gp.path -BOM $BOM_Name
    if ($found) {
        $grepSource = $gp.source
        $grepFound = $found
        break
    }
}

if ($grepFound) {
    if ($grepFound -is [hashtable] -and $grepFound.multiple) {
        $result = @{
            found = $true
            source = "grep"
            search_source = $grepSource
            path = $grepFound.path
            multiple = $true
            count = $grepFound.count
        }
    } else {
        $result = @{
            found = $true
            source = "grep"
            search_source = $grepSource
            path = $grepFound
            multiple = $false
        }
    }
    $result | ConvertTo-Json | Write-Output
} else {
    @{ found = $false; source = "grep" } | ConvertTo-Json | Write-Output
}
