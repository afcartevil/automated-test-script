# 产物仓创建子技能执行工作流

## 工作流概述
本工作流负责将 MODEM 产物仓从目标分支公共仓复制到 AP 工程的 vendor 路径下。

## 详细执行步骤

### 步骤 1：接收参数
```powershell
# 从上下文获取参数
$BOM_Name_Target = $context.BOM_Name_Target  # 更新后的 BOM 仓名字
$Path_B_Pub = $context.Path_B_Pub            # 目标分支公共仓路径
$AP_Vendor_Path = "Z:\U-AP\vendor\mediatek\proprietary\modem"  # 默认路径

# 参数验证
if (-not $BOM_Name_Target) {
    Write-Error "缺少参数：BOM_Name_Target"
    return @{ success = $false; message = "缺少参数：BOM_Name_Target" }
}
if (-not $Path_B_Pub) {
    Write-Error "缺少参数：Path_B_Pub"
    return @{ success = $false; message = "缺少参数：Path_B_Pub" }
}
```

### 步骤 2：询问用户产物是否已编译完成
```powershell
Write-Host "`n【产物仓创建】"
Write-Host "请确认：$BOM_Name_Target 项目的产物是否已编译完成？"
$response = Read-Host "请输入 '是' 或 '否'"

if ($response -ne "是") {
    Write-Information "用户表示产物未编译完成，跳过产物仓创建步骤"
    return @{ 
        success = $true 
        message = "用户表示产物未编译完成，已跳过产物仓创建" 
    }
}
```

### 步骤 3：定位产物仓文件夹
```powershell
Write-Information "正在查找产物仓文件夹..."

# 在 Path_B_Pub 下查找包含 "-out_vnd" 的文件夹
$sourceFolderPattern = "*$BOM_Name_Target-out_vnd*"
$sourceFolder = Get-ChildItem -Path $Path_B_Pub -Filter $sourceFolderPattern -Directory

if (-not $sourceFolder) {
    Write-Warning "未找到产物仓文件夹：$sourceFolderPattern"
    Write-Warning "请确认产物是否已编译完成"
    return @{ 
        success = $false 
        message = "未找到产物仓文件夹：$sourceFolderPattern" 
    }
}

Write-Information "找到产物仓文件夹：$($sourceFolder.FullName)"
```

### 步骤 4：验证目标路径
```powershell
Write-Information "正在验证目标路径..."

# 检查目标路径是否存在，不存在则创建
if (-not (Test-Path -Path $AP_Vendor_Path)) {
    Write-Information "目标路径不存在，正在创建：$AP_Vendor_Path"
    New-Item -Path $AP_Vendor_Path -ItemType Directory -Force | Out-Null
}

# 检查目标文件夹是否已存在
$targetFolder = Join-Path -Path $AP_Vendor_Path -ChildPath $BOM_Name_Target
if (Test-Path -Path $targetFolder) {
    Write-Warning "目标文件夹已存在：$targetFolder"
    $overwrite = Read-Host "是否覆盖已存在的文件夹？（是/否）"
    if ($overwrite -eq "是") {
        Write-Information "正在删除已存在的文件夹..."
        Remove-Item -Path $targetFolder -Recurse -Force
    } else {
        Write-Information "用户选择不覆盖，跳过复制"
        return @{ 
            success = $true 
            message = "用户选择不覆盖已存在的文件夹" 
        }
    }
}
```

### 步骤 5：复制产物仓文件夹
```powershell
Write-Information "正在复制产物仓文件夹..."

try {
    # 使用 Robocopy 复制文件夹（支持长路径和特殊字符）
    robocopy $sourceFolder.FullName $targetFolder /E /COPYALL /R:3 /W:5 /NP
    
    # 检查复制结果（Robocopy 返回 0-7 表示成功）
    if ($LASTEXITCODE -le 7) {
        Write-Information "产物仓复制成功"
    } else {
        Write-Error "产物仓复制失败，Robocopy 返回码：$LASTEXITCODE"
        return @{ 
            success = $false 
            message = "产物仓复制失败，Robocopy 返回码：$LASTEXITCODE" 
        }
    }
} catch {
    Write-Error "复制过程中发生错误：$_"
    return @{ 
        success = $false 
        message = "复制过程中发生错误：$_" 
    }
}
```

### 步骤 6：验证复制结果
```powershell
Write-Information "正在验证复制结果..."

# 检查目标文件夹是否存在
if (-not (Test-Path -Path $targetFolder)) {
    Write-Error "复制失败，目标文件夹不存在"
    return @{ 
        success = $false 
        message = "复制失败，目标文件夹不存在" 
    }
}

# 统计复制的文件数量
$copiedFilesCount = (Get-ChildItem -Path $targetFolder -Recurse -File | Measure-Object).Count
Write-Information "成功复制 $copiedFilesCount 个文件"
```

### 步骤 7：返回结果
```powershell
return @{
    success = $true
    message = "产物仓创建完成"
    source_folder = $sourceFolder.FullName
    target_folder = $targetFolder
    copied_files_count = $copiedFilesCount
}
```

## 异常处理流程
1. **参数缺失**：返回错误信息并终止执行
2. **产物仓不存在**：提示用户确认产物是否已编译，返回失败
3. **目标路径不存在**：自动创建目标路径
4. **目标文件夹已存在**：询问用户是否覆盖
5. **复制失败**：记录错误信息并返回失败

## 安全机制
- 使用 Robocopy 进行文件夹复制，支持长路径和特殊字符
- 复制前自动检查目标文件夹是否存在
- 支持用户确认覆盖操作
- 复制完成后验证目标文件夹存在性

## 示例输出
```
【产物仓创建】
请确认：x6856_h971_a1 项目的产物是否已编译完成？
请输入 '是' 或 '否': 是
正在查找产物仓文件夹...
找到产物仓文件夹：Z:\modem\S\99U\TK_MD_MOLY.NR17.R1.MP3.RC.MP_U0\x6856_h971_a1-out_vnd
正在验证目标路径...
正在复制产物仓文件夹...
成功复制 156 个文件
产物仓创建完成
```