# P1 大版本升级主控工作流（集成 MODEM + AP）

## 工作流概述
本工作流实现 MODEM_SKILL 和 AP_SKILL 的集成，实现参数的统一管理和传递，减少用户重复输入。

## 子技能路径配置

### 技能目录结构
```
P1_UPGRADE_SKILL/
├── SKILL.md                          # 主控技能配置
├── scripts/
│   └── master_execution_workflow.md  # 主控执行工作流
├── MODEM_SKILL/                      # MODEM 侧子技能
│   ├── rf_param_skill/               # RF 参数移植
│   ├── macro_control_skill/          # 宏控移植
│   └── lock_nv_skill/                # 锁卡 NV 修改
└── AP_SKILL/                         # AP 侧子技能
    ├── project_file_skill/           # 工程文件修改
    ├── gpio_check_skill/             # GPIO 检查
    └── product_repo_skill/           # 产物仓创建
```

### 子技能路径映射
```powershell
$skillPaths = @{
    rf_param_skill = "./MODEM_SKILL/rf_param_skill/"
    macro_control_skill = "./MODEM_SKILL/macro_control_skill/"
    lock_nv_skill = "./MODEM_SKILL/lock_nv_skill/"
    project_file_skill = "./AP_SKILL/project_file_skill/"
    gpio_check_skill = "./AP_SKILL/gpio_check_skill/"
    product_repo_skill = "./AP_SKILL/product_repo_skill/"
}
```

### 子技能加载函数
```powershell
function Load-Skill {
    param(
        [string]$SkillName
    )
    
    # 获取技能路径
    $skillPath = $skillPaths[$SkillName]
    if (-not $skillPath) {
        Write-Error "未知技能：$SkillName"
        return $null
    }
    
    # 构建完整路径
    $skillFullPath = Join-Path -Path $PWD.Path -ChildPath $skillPath
    
    # 检查技能目录是否存在
    if (-not (Test-Path -Path $skillFullPath)) {
        Write-Error "技能目录不存在：$skillFullPath"
        return $null
    }
    
    # 检查 SKILL.md 是否存在
    $skillConfigPath = Join-Path -Path $skillFullPath -ChildPath "SKILL.md"
    if (-not (Test-Path -Path $skillConfigPath)) {
        Write-Error "技能配置文件不存在：$skillConfigPath"
        return $null
    }
    
    Write-Information "成功加载技能：$SkillName ($skillFullPath)"
    return @{
        name = $SkillName
        path = $skillFullPath
        config_path = $skillConfigPath
        loaded = $true
    }
}

### 子技能调用函数
function Invoke-Skill {
    param(
        [string]$SkillName,
        [hashtable]$Parameters
    )
    
    # 加载技能
    $skill = Load-Skill -SkillName $SkillName
    if (-not $skill.loaded) {
        return @{ success = $false; message = "无法加载技能：$SkillName" }
    }
    
    Write-Information "调用子技能：$SkillName"
    Write-Information "参数：$($Parameters | ConvertTo-Json -Compress)"
    
    # 构建执行工作流路径
    $workflowPath = Join-Path -Path $skill.path -ChildPath "scripts/ai_execution_workflow.md"
    
    # 检查工作流文件是否存在
    if (-not (Test-Path -Path $workflowPath)) {
        Write-Error "工作流文件不存在：$workflowPath"
        return @{ success = $false; message = "工作流文件不存在：$workflowPath" }
    }
    
    # 执行子技能逻辑
    # 实际实现中这里会执行工作流文件中的逻辑
    # 并将 Parameters 传递给子技能
    
    # 模拟执行（实际实现中会调用真正的执行逻辑）
    Start-Sleep -Milliseconds 500
    
    Write-Information "子技能 $SkillName 执行完成"
    return @{ success = $true; message = "执行成功" }
}
```

## 详细执行步骤

### 阶段 0：技能初始化
```powershell
Write-Host "`n【P1 大版本升级 - 技能初始化】"
Write-Host "正在加载子技能..."

# 加载所有子技能
$loadedSkills = @()
foreach ($skillName in $skillPaths.Keys) {
    $skill = Load-Skill -SkillName $skillName
    if ($skill.loaded) {
        $loadedSkills += $skillName
    }
}

Write-Information "成功加载 $($loadedSkills.Count) 个子技能：$($loadedSkills -join ', ')"

if ($loadedSkills.Count -eq 0) {
    Write-Error "未加载任何子技能，请检查技能目录结构"
    return @{ success = $false; message = "未加载任何子技能" }
}
```

### 阶段 1：参数收集（一次性收集所有参数）

#### 1.1 收集 MODEM 侧参数
```powershell
Write-Host "`n【P1 大版本升级 - 参数收集】"
Write-Host "请输入 MODEM 侧参数："

$globalContext = @{}

# 原分支路径
$globalContext.Path_A_Pub = Read-Host "原分支公共仓路径（Path_A_Pub）"
$globalContext.Path_A_Priv = Read-Host "原分支私有仓路径（Path_A_Priv）"

# 目标分支路径
$globalContext.Path_B_Pub = Read-Host "目标分支公共仓路径（Path_B_Pub）"
$globalContext.Path_B_Priv = Read-Host "目标分支私有仓路径（Path_B_Priv）"

# BOM 信息
$globalContext.BOM_Name = Read-Host "原 BOM 名称（BOM_Name）"
$globalContext.BOM_Name_Target = Read-Host "更新后的 BOM 名称（BOM_Name_Target）"

# RF 参数目标位置
$globalContext.RF_TARGET_LOCATION = Read-Host "RF 参数目标位置（public/private）"
```

#### 1.2 收集 AP 侧参数
```powershell
Write-Host "`n请输入 AP 侧参数："

# AP 工程路径
$globalContext.AP_Project_Path = Read-Host "AP 工程文件代码路径（AP_Project_Path）"

# GPIO 检查路径
$globalContext.GPIO_Path_C = Read-Host "GPIO 检查升级前路径（GPIO_Path_C）"
$globalContext.GPIO_Path_D = Read-Host "GPIO 检查升级后路径（GPIO_Path_D）"

# 是否为 TOS16 之前版本
$isTOS16 = Read-Host "是否为 TOS16 之前的版本？（是/否）"
$globalContext.Is_TOS16_Before = ($isTOS16 -eq "是")
```

#### 1.3 参数验证
```powershell
Write-Host "`n正在验证参数..."

# 验证 MODEM 侧必需参数
$modemRequiredParams = @("Path_A_Pub", "Path_A_Priv", "Path_B_Pub", "Path_B_Priv", 
                         "BOM_Name", "BOM_Name_Target", "RF_TARGET_LOCATION")
foreach ($param in $modemRequiredParams) {
    if (-not $globalContext[$param]) {
        Write-Error "缺少必需参数：$param"
        return @{ success = $false; message = "缺少必需参数：$param" }
    }
}

# 验证路径有效性
foreach ($pathParam in @("Path_A_Pub", "Path_A_Priv", "Path_B_Pub", "Path_B_Priv")) {
    if (-not (Test-Path -Path $globalContext[$pathParam])) {
        Write-Warning "路径不存在：$($globalContext[$pathParam])"
    }
}

Write-Information "参数收集完成，共收集 $($globalContext.Count) 个参数"
```

---

### 阶段 2：MODEM 侧处理

#### 2.1 RF 参数移植
```powershell
Write-Host "`n【阶段 2.1】RF 参数移植"

$rfParams = @{
    Path_A_Pub = $globalContext.Path_A_Pub
    Path_A_Priv = $globalContext.Path_A_Priv
    Path_B_Pub = $globalContext.Path_B_Pub
    Path_B_Priv = $globalContext.Path_B_Priv
    BOM_Name = $globalContext.BOM_Name
    BOM_Name_Target = $globalContext.BOM_Name_Target
    RF_TARGET_LOCATION = $globalContext.RF_TARGET_LOCATION
}

# 调用 RF 参数移植子技能
$rfResult = Invoke-Skill -SkillName "rf_param_skill" -Parameters $rfParams

if ($rfResult.success) {
    Write-Information "RF 参数移植成功"
    $globalContext.modem_result.rf_success = $true
} else {
    Write-Warning "RF 参数移植失败：$($rfResult.message)"
    $globalContext.modem_result.rf_success = $false
}
```

#### 2.2 宏控移植
```powershell
Write-Host "`n【阶段 2.2】宏控移植"

$macroParams = @{
    Path_A_Pub = $globalContext.Path_A_Pub
    Path_A_Priv = $globalContext.Path_A_Priv
    Path_B_Pub = $globalContext.Path_B_Pub
    Path_B_Priv = $globalContext.Path_B_Priv
    BOM_Name = $globalContext.BOM_Name
    BOM_Name_Target = $globalContext.BOM_Name_Target
}

# 调用宏控移植子技能
$macroResult = Invoke-Skill -SkillName "macro_control_skill" -Parameters $macroParams

if ($macroResult.success) {
    Write-Information "宏控移植成功"
    $globalContext.modem_result.macro_success = $true
} else {
    Write-Warning "宏控移植失败：$($macroResult.message)"
    $globalContext.modem_result.macro_success = $false
}
```

#### 2.3 锁卡 NV 修改（可选）
```powershell
Write-Host "`n【阶段 2.3】锁卡 NV 修改"

$response = Read-Host "是否需要修改锁卡 NV？（是/否）"
if ($response -eq "是") {
    $lockNvParams = @{
        Path_B_Pub = $globalContext.Path_B_Pub
        BOM_Name_Target = $globalContext.BOM_Name_Target
    }

    # 调用锁卡 NV 修改子技能
    $lockNvResult = Invoke-Skill -SkillName "lock_nv_skill" -Parameters $lockNvParams

    if ($lockNvResult.success) {
        Write-Information "锁卡 NV 修改成功"
        $globalContext.modem_result.lock_nv_success = $true
    } else {
        Write-Warning "锁卡 NV 修改失败：$($lockNvResult.message)"
        $globalContext.modem_result.lock_nv_success = $false
    }
} else {
    Write-Information "跳过锁卡 NV 修改"
    $globalContext.modem_result.lock_nv_success = $null
}
```

---

### 阶段 3：AP 侧处理（可选）

#### 3.0 询问是否执行 AP 侧处理
```powershell
Write-Host "`n【阶段 3】AP 侧处理"

$response = Read-Host "是否需要执行 AP 侧处理？（是/否）"
if ($response -ne "是") {
    Write-Information "跳过 AP 侧处理"
    $globalContext.ap_result = @{ skipped = $true }
    goto :FinalSummary
}
```

#### 3.1 工程文件修改
```powershell
Write-Host "`n【阶段 3.1】工程文件修改"

# 调用 ModifyProjectConfig.ps1 脚本
$projectScript = Join-Path $PWD.Path "AP_SKILL/project_file_skill/scripts/ModifyProjectConfig.ps1"
$projectResult = & $projectScript `
    -BOM_Name_Target $globalContext.BOM_Name_Target `
    -AP_Project_Path $globalContext.AP_Project_Path

if ($projectResult.success) {
    Write-Information $projectResult.message
    $globalContext.ap_result.project_file_success = $true
} else {
    Write-Warning "工程文件修改失败：$($projectResult.error)"
    $globalContext.ap_result.project_file_success = $false
}
```

#### 3.2 GPIO 检查
```powershell
Write-Host "`n【阶段 3.2】GPIO 检查"

# Step 1: 先查看差异（不加 -AutoApply）
$gpioScript = Join-Path $PWD.Path "AP_SKILL/gpio_check_skill/scripts/GpioCheckModify.ps1"
$diffResult = & $gpioScript `
    -BOM_Name_Target $globalContext.BOM_Name_Target `
    -Path_C $globalContext.GPIO_Path_C `
    -Path_D $globalContext.GPIO_Path_D `
    -Is_TOS16_Before $globalContext.Is_TOS16_Before

# Step 2: 向用户展示差异，确认是否修改
if ($diffResult.success -and $diffResult.modified_count -eq 0 -and $diffResult.differences.Count -gt 0) {
    $response = Read-Host "发现 $($diffResult.differences.Count) 处 GPIO 差异，是否应用修改？（是/否）"
    if ($response -eq "是") {
        $applyResult = & $gpioScript `
            -BOM_Name_Target $globalContext.BOM_Name_Target `
            -Path_C $globalContext.GPIO_Path_C `
            -Path_D $globalContext.GPIO_Path_D `
            -Is_TOS16_Before $globalContext.Is_TOS16_Before `
            -AutoApply
        if ($applyResult.success) {
            Write-Information "GPIO 检查完成，已应用 $($applyResult.modified_count) 处修改"
            $globalContext.ap_result.gpio_success = $true
            $globalContext.ap_result.gpio_modified_count = $applyResult.modified_count
        } else {
            Write-Warning "GPIO 修改失败：$($applyResult.message)"
            $globalContext.ap_result.gpio_success = $false
        }
    }
} elseif ($diffResult.success) {
    Write-Information $diffResult.message
    $globalContext.ap_result.gpio_success = $true
} else {
    Write-Warning "GPIO 检查失败：$($diffResult.message)"
    $globalContext.ap_result.gpio_success = $false
}
```

#### 3.3 产物仓创建
```powershell
Write-Host "`n【阶段 3.3】产物仓创建"

$productRepoParams = @{
    BOM_Name_Target = $globalContext.BOM_Name_Target  # 继承自 MODEM
    Path_B_Pub = $globalContext.Path_B_Pub            # 继承自 MODEM
    AP_Vendor_Path = "$($globalContext.AP_Project_Path)\..\mediatek\proprietary\modem"
}

# 调用产物仓创建子技能
$productRepoResult = Invoke-Skill -SkillName "product_repo_skill" -Parameters $productRepoParams

if ($productRepoResult.success) {
    Write-Information "产物仓创建成功"
    $globalContext.ap_result.product_repo_success = $true
} else {
    Write-Warning "产物仓创建失败：$($productRepoResult.message)"
    $globalContext.ap_result.product_repo_success = $false
}
```

---

### 阶段 4：结果汇总

#### 4.1 输出汇总报告
```powershell
:FinalSummary
Write-Host "`n【阶段 4】结果汇总"
Write-Host "=" * 60

# MODEM 侧结果
Write-Host "`n【MODEM 侧处理结果】"
Write-Host "├─ RF 参数移植：$($globalContext.modem_result.rf_success ? '成功' : '失败')"
Write-Host "├─ 宏控移植：$($globalContext.modem_result.macro_success ? '成功' : '失败')"
Write-Host "└─ 锁卡 NV 修改：$(if ($null -eq $globalContext.modem_result.lock_nv_success) { '未执行' } else { ($globalContext.modem_result.lock_nv_success ? '成功' : '失败') })"

# AP 侧结果
Write-Host "`n【AP 侧处理结果】"
if ($globalContext.ap_result.skipped) {
    Write-Host "└─ AP 侧处理：未执行"
} else {
    Write-Host "├─ 工程文件修改：$($globalContext.ap_result.project_file_success ? '成功' : '失败')"
    Write-Host "├─ GPIO 检查：$($globalContext.ap_result.gpio_success ? '成功' : '失败')"
    Write-Host "└─ 产物仓创建：$($globalContext.ap_result.product_repo_success ? '成功' : '失败')"
}

# 整体结果
$overallSuccess = $globalContext.modem_result.rf_success -and 
                  $globalContext.modem_result.macro_success -and
                  (-not $globalContext.ap_result.skipped -or 
                   ($globalContext.ap_result.project_file_success -and 
                    $globalContext.ap_result.gpio_success -and 
                    $globalContext.ap_result.product_repo_success))

Write-Host "`n【整体结果】"
Write-Host "P1 大版本升级：$(if ($overallSuccess) { '成功' } else { '部分完成' })"

if (-not $overallSuccess) {
    Write-Host "请检查上述失败项并手动处理"
}
```

#### 4.2 返回结果
```powershell
return @{
    success = $overallSuccess
    message = "P1 大版本升级完成"
    global_context = $globalContext
    modem_result = $globalContext.modem_result
    ap_result = $globalContext.ap_result
}
```

---

## 参数传递关系表

| 参数名 | 来源 | 传递到 | 用途 |
|--------|------|--------|------|
| BOM_Name_Target | 用户输入 | RF、宏控、锁卡NV、工程文件、GPIO、产物仓 | 所有子技能的核心参数 |
| Path_B_Pub | 用户输入 | RF、宏控、锁卡NV、产物仓 | 目标分支公共仓路径 |
| Path_A_Pub | 用户输入 | RF、宏控 | 原分支公共仓路径 |
| Path_A_Priv | 用户输入 | RF、宏控 | 原分支私有仓路径 |
| Path_B_Priv | 用户输入 | RF、宏控 | 目标分支私有仓路径 |
| RF_TARGET_LOCATION | 用户输入 | RF | RF 参数目标位置 |
| AP_Project_Path | 用户输入 | 工程文件 | AP 工程路径 |
| GPIO_Path_C | 用户输入 | GPIO | GPIO 检查升级前路径 |
| GPIO_Path_D | 用户输入 | GPIO | GPIO 检查升级后路径 |
| Is_TOS16_Before | 用户输入 | GPIO | TOS16 版本判断 |

---

## 技能调用协议

### 子技能调用格式
```powershell
function Invoke-Skill {
    param(
        [string]$SkillName,
        [hashtable]$Parameters
    )
    
    Write-Information "调用子技能：$SkillName"
    Write-Information "参数：$($Parameters | ConvertTo-Json -Compress)"
    
    # 实际调用子技能的逻辑
    # ...
    
    return @{ success = $true; message = "执行成功" }
}
```

### 子技能调用列表

| 子技能名称 | 技能路径 | 调用时机 |
|------------|----------|----------|
| rf_param_skill | MODEM_SKILL/rf_param_skill | 阶段 2.1 |
| macro_control_skill | MODEM_SKILL/macro_control_skill | 阶段 2.2 |
| lock_nv_skill | MODEM_SKILL/lock_nv_skill | 阶段 2.3（可选） |
| project_file_skill | AP_SKILL/project_file_skill | 阶段 3.1 |
| gpio_check_skill | AP_SKILL/gpio_check_skill | 阶段 3.2 |
| product_repo_skill | AP_SKILL/product_repo_skill | 阶段 3.3 |

---

## 异常处理流程

### 参数缺失
```powershell
# 如果缺少必需参数，终止执行
if (-not $globalContext.BOM_Name_Target) {
    Write-Error "缺少必需参数：BOM_Name_Target"
    return @{ success = $false; message = "缺少必需参数：BOM_Name_Target" }
}
```

### 子技能失败处理
```powershell
# MODEM 侧失败后询问是否继续
if (-not $rfResult.success) {
    $continue = Read-Host "RF 参数移植失败，是否继续执行后续步骤？（是/否）"
    if ($continue -ne "是") {
        return @{ success = $false; message = "用户选择终止" }
    }
}
```

### 路径验证
```powershell
# 验证所有路径
$pathsToCheck = @(
    $globalContext.Path_A_Pub,
    $globalContext.Path_A_Priv,
    $globalContext.Path_B_Pub,
    $globalContext.Path_B_Priv
)

foreach ($path in $pathsToCheck) {
    if (-not (Test-Path -Path $path)) {
        Write-Warning "路径不存在：$path"
    }
}
```

---

## 安全机制

### 参数验证
- 检查所有必需参数是否存在
- 验证路径是否有效
- 验证参数格式（如 RF_TARGET_LOCATION 只能是 public 或 private）

### 操作日志
```powershell
# 记录操作日志
$logEntry = @{
    timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    action = "P1_UPGRADE_SKILL"
    parameters = $globalContext
    result = $overallSuccess
}

# 保存日志到文件
$logEntry | ConvertTo-Json | Out-File -FilePath "P1_upgrade_log_$(Get-Date -Format 'yyyyMMdd_HHmmss').json"
```

### 自动备份
```powershell
# 在修改关键文件前自动备份
function Backup-File {
    param([string]$FilePath)
    $backupPath = "$FilePath.backup_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
    Copy-Item -Path $FilePath -Destination $backupPath
    Write-Information "已备份文件：$backupPath"
}
```