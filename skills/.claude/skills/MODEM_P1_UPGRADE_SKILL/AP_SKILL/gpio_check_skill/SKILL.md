---
name: gpio-check-skill
description: 对比升级前后 .dws 文件中 SIM/BPI/MIPI/HOT_PLUG 的 GPIO 配置差异并根据差异自动修改。当用户提到 "GPIO 检查"、"dws 对比" 时触发。差异对比必须使用 scripts/GpioCheckModify.ps1，禁止自行构造对比或修改逻辑。
version: 2.0.0
tools: Read, Bash
---

# GPIO 检查子技能

## 技能定位
本技能负责对比升级前后两个版本的 .dws 文件中 GPIO 配置的差异，包括 SIM、BPI、MIPI、HOT_PLUG 相关的 GPIO 配置，并自动将源分支配置应用到目标分支。

## 输入参数
| 参数名 | 类型 | 描述 | 必填 |
|--------|------|------|------|
| BOM_Name_Target | string | 更新后的 BOM 仓名字（从 MODEM_SKILL 继承） | 是 |
| Path_C | string | 升级前的 .dws 文件所在路径（用户输入） | 是 |
| Path_D | string | 升级后的 .dws 文件所在路径（用户输入） | 是 |
| Is_TOS16_Before | boolean | 是否为 TOS16 之前的版本（用户选择） | 是 |

## 输出结果
| 输出项 | 类型 | 描述 |
|--------|------|------|
| success | boolean | 操作是否成功 |
| message | string | 执行结果描述 |
| differences | array | 发现的差异列表 |
| modified_count | integer | 修改的 GPIO 数量 |
| drdi_result | object | DRDI 检查结果 |

## 执行流程
1. **接收参数**：接收 BOM_Name_Target、Path_C、Path_D、Is_TOS16_Before 参数
2. **路径验证**：验证路径有效性
3. **执行 GPIO 检查脚本**（使用 `scripts/GpioCheckModify.ps1`）：
   - 先不加 `-AutoApply` 运行，展示差异
   - 向用户展示差异结果，确认是否修改
   - 如需修改，执行 `scripts/ApplyGpioDifferences.ps1` 应用所有 GPIO 差异（以源文件为准）
4. **展示 DRDI 检查结果**：脚本自动检查 DRDI ADC 配置
5. **返回结果**：返回执行结果

## 硬约束（必须遵守）
1. **差异对比只能用 GpioCheckModify.ps1**：必须通过 `scripts/GpioCheckModify.ps1` 执行差异对比。**禁止**自行构造 Select-String、Edit 或其他对比命令
2. **应用修改只能用 ApplyGpioDifferences.ps1**：用户确认后，使用 `scripts/ApplyGpioDifferences.ps1` 应用所有差异。**禁止**自行构造 Edit 或正则替换命令
3. **不读取脚本内容**：直接执行脚本即可，不需要阅读脚本源码
4. **首次运行不加 -AutoApply**：先展示差异，确认后再执行应用脚本
5. **一切以源文件为准**：源有目标无→复制，源目标都有但不同→用源覆盖，源无目标有→删除。GPIO、md1_eint、ADC 全部自动处理
6. **如果 JSON 输出中 differences 数组为空但 message 说有差异**：直接询问用户是否需要应用修改。**禁止**反复尝试捕获输出、手动 diff 整个 .dws 文件、或自行猜测差异内容
7. **缩进必须保持一致**：ApplyGpioDifferences.ps1 脚本会自动处理缩进（保留目标文件的 GPIO 缩进格式）。**禁止** agent 在脚本执行后自行修改 .dws 文件中的缩进或格式。如果应用后发现缩进问题，应修复脚本而非手动编辑 .dws 文件

## 调用示例

### 仅查看差异
```
powershell -ExecutionPolicy Bypass -File "scripts/GpioCheckModify.ps1" ^
    -BOM_Name_Target "{BOM_Name_Target}" ^
    -Path_C "{Path_C}" ^
    -Path_D "{Path_D}" ^
    -Is_TOS16_Before {Is_TOS16_Before}
```

### 应用修改（以源文件为准）
```
powershell -ExecutionPolicy Bypass -File "scripts/ApplyGpioDifferences.ps1" ^
    -SourcePath "{source_dws_file}" ^
    -TargetPath "{target_dws_file}" ^
    -GpioNums "103,111,114,115,116,117,119,120,121"
```

**自动处理所有差异（以源文件为准）：**
- GPIO 配置：源有目标无→复制，都有但不同→用源覆盖，源无目标有→删除
- md1_eint 模块：同上逻辑自动替换/复制/删除
- ADC (DRDI) 配置：同上逻辑自动替换/复制/删除

## 异常处理
1. **路径无效**：脚本返回错误信息
2. **.dws 文件不存在**：脚本返回错误信息
3. **.fig 文件不存在**：脚本返回错误信息
4. **无差异发现**：脚本返回"无差异"，直接退出