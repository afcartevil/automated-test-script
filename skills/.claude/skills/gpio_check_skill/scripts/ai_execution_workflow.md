# GPIO 检查子技能执行工作流

## 工作流概述
本工作流定义了 GPIO 检查子技能的完整执行流程，用于对比升级前后 .dws 文件中 GPIO 配置的差异并自动修改。

## 执行步骤

### 步骤 1：接收参数
接收来自主控技能或用户的输入参数：
- **BOM_Name_Target**：更新后的 BOM 仓名字（从 MODEM_SKILL 继承）
- **Path_C**：升级前的 .dws 文件所在路径（用户输入）
- **Path_D**：升级后的 .dws 文件所在路径（用户输入）
- **Is_TOS16_Before**：是否为 TOS16 之前的版本（用户选择）

### 步骤 2：路径验证
检查 Path_C 和 Path_D 是否有效，根据版本类型验证路径格式：
- TOS16 之前：路径应包含 `tran_projects`
- TOS16 及之后：路径应包含 `vendor`

### 步骤 3：执行差异对比（不加 -AutoApply）
```
powershell -ExecutionPolicy Bypass -File "scripts/GpioCheckModify.ps1" ^
    -BOM_Name_Target "{BOM_Name_Target}" ^
    -Path_C "{Path_C}" ^
    -Path_D "{Path_D}" ^
    -Is_TOS16_Before {Is_TOS16_Before}
```

脚本内部完成：
1. 定位 .dws 文件（在 Path_C 和 Path_D 下查找包含 BOM_Name_Target 的 .dws）
2. 定位 .fig 文件（提取平台号如 mt6878，查找对应的 .fig 文件）
3. 从 .fig 文件提取 BPI、MIPI、HOT_PLUG 相关 GPIO 编号
4. 从 .dws 文件提取 SIM 相关 GPIO 编号
5. 对比四类 GPIO（SIM/HOT_PLUG/BPI/MIPI）的配置差异
6. DRDI 检查（ADC_FDD_RF_PARAMS_DYNAMIC_CUSTOM_CH 配置一致性）

### 步骤 4：展示差异结果
解析脚本返回的 JSON 输出，向用户展示：
- 各类别（SIM/HOT_PLUG/BPI/MIPI）的 GPIO 差异
- DRDI 检查结果
- 差异总数

### 步骤 5：确认修改并应用
如果用户确认需要修改差异，执行应用脚本：
```
powershell -ExecutionPolicy Bypass -File "scripts/ApplyGpioDifferences.ps1" ^
    -SourcePath "{targetDwsFile_C}" ^
    -TargetPath "{targetDwsFile_D}" ^
    -GpioNums "gpioNum1,gpioNum2,..."
```

**应用规则（以源文件为准）：**
- GPIO 配置：源有、目标无 → 从源复制到目标；都有但不同 → 用源覆盖；源无、目标有 → 删除
- md1_eint 模块：同上逻辑自动处理
- ADC (DRDI) 配置：同上逻辑自动处理

应用完成后，重新执行 `GpioCheckModify.ps1` 验证无差异残留。

### 步骤 6：返回结果
解析脚本返回的 JSON 输出，返回：
- success: 是否成功
- modified_count: 修改的 GPIO 数量
- differences: 差异详情
- drdi_result: DRDI 检查结果

## 硬约束（必须遵守）
1. **差异对比和修改只能用脚本**：步骤3和步骤5必须通过 `GpioCheckModify.ps1` 执行。**禁止**自行构造 Select-String、Edit 或其他对比/修改命令
2. **不读取脚本内容**：直接执行脚本即可，不需要阅读脚本源码
3. **首次运行不加 -AutoApply**：先展示差异，确认后再加 `-AutoApply` 执行修改
4. **DRDI 检查由脚本自动完成**：脚本会检查 ADC 配置并返回结果，不需要额外操作

## 异常处理
1. **路径不存在**：脚本返回错误信息
2. **文件不存在**：脚本返回错误信息（.dws/.fig）
3. **平台号提取失败**：脚本返回错误信息
4. **无差异**：脚本返回"无差异"，直接退出

## 输出示例

### 有差异（未应用）
```json
{
  "success": true,
  "message": "Found 3 GPIO difference(s). Use -AutoApply to apply changes.",
  "differences": [
    { "gpioNum": "24", "category": "SIM", "configC": "configured", "configD": "not_configured", "hasDiff": true }
  ],
  "modified_count": 0,
  "drdi_result": { "found": true, "adc_num": "adc0", "status": "consistent" }
}
```

### 已应用修改
```json
{
  "success": true,
  "message": "Applied 3 GPIO configuration(s) from source to target",
  "differences": [
    { "gpioNum": "24", "category": "SIM", "configC": "configured", "configD": "not_configured", "hasDiff": true }
  ],
  "modified_count": 3,
  "drdi_result": { "found": true, "adc_num": "adc0", "status": "consistent" }
}
```

### 无差异
```json
{
  "success": true,
  "message": "No GPIO configuration differences found",
  "differences": [],
  "modified_count": 0,
  "drdi_result": { "found": false, "status": "not_found_contact_rf" }
}
```
