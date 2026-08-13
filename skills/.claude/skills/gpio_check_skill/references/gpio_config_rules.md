# GPIO 配置对比规范

## 概述
本参考文档定义了 GPIO 配置对比的规范和最佳实践，确保升级过程中 GPIO 配置的一致性。

## GPIO 分类标准

### SIM 相关 GPIO
| 信号类型 | 命名规则 | 示例 |
|----------|----------|------|
| SIM 时钟 | GPIO_SIM*_SCLK | GPIO_SIM1_SCLK |
| SIM 复位 | GPIO_SIM*_SRST | GPIO_SIM1_SRST |
| SIM 数据 | GPIO_SIM*_SIO | GPIO_SIM1_SIO |
| SIM 热插拔 | GPIO_SIM*_HOT_PLUG | GPIO_SIM1_HOT_PLUG |

### BPI 相关 GPIO
- MODE1 包含 `BPI_BUS` 的 GPIO
- 通常用于基带处理器接口

### MIPI 相关 GPIO
| 信号类型 | 命名规则 | 示例 |
|----------|----------|------|
| MIPI 时钟 | MIPI*_D_SCLK | MIPI0_D_SCLK |
| MIPI 数据 | MIPI*_D_SDATA | MIPI0_D_SDATA |
| MIPI 主时钟 | MIPI_M_SCLK | MIPI_M_SCLK |
| MIPI 主数据 | MIPI_M_SDATA | MIPI_M_SDATA |

## 配置项对比规则

### 必须对比的配置项
| 配置项 | 说明 | 取值范围 |
|--------|------|----------|
| eint_mode | 是否启用中断模式 | true/false |
| def_mode | 默认模式 | 0-7 |
| inpull_en | 是否启用上拉/下拉 | true/false |
| inpull_selhigh | 上拉还是下拉 | true(上拉)/false(下拉) |
| def_dir | 默认方向 | IN/OUT |
| out_high | 默认输出电平 | true/false |
| smt | 是否启用施密特触发器 | true/false |
| ies | 是否反转输入使能 | true/false |

### 配置项优先级
1. **高优先级**：def_mode, def_dir, inpull_en
2. **中优先级**：eint_mode, out_high
3. **低优先级**：smt, ies

## 差异处理策略

### SIM 相关差异
- **IN/OUT 方向不一致**：通常需要修改为与升级前一致
- **上拉/下拉配置不一致**：需要确认硬件设计是否变更
- **def_mode 不一致**：检查是否涉及功能复用

### BPI 相关差异
- **NC 配置差异**：如果升级前是 NC，升级后有值，需要确认是否需要保持 NC
- **模式配置差异**：检查是否涉及 BPI_BUS 复用

### MIPI 相关差异
- **高速信号配置**：特别注意 inpull_en 和 smt 配置
- **时钟信号配置**：确保驱动能力一致

## 安全检查清单

### 检查项
- [ ] 所有 GPIO 配置项是否完整对比
- [ ] 是否有遗漏的 GPIO 编号
- [ ] 平台号提取是否正确
- [ ] .fig 文件路径是否正确
- [ ] .dws 文件解析是否正确

### 危险配置变更
- **def_mode 从 NC 变为有值**：可能导致引脚功能变化
- **def_dir 从 IN 变为 OUT**：可能导致硬件冲突
- **inpull_en 从 true 变为 false**：可能影响信号稳定性

## DRDI 检查规范

### DRDI 概述
DRDI（Dynamic RF Parameters Dynamic Customization，射频参数动态定制）是一种用于动态配置射频参数的机制。

### DRDI 配置查找流程
```
1. 在 C 的 .dws 文件中搜索 ADC_FDD_RF_PARAMS_DYNAMIC_CUSTOM_CH
   ↓
2. 如果找到：
   - 确定是哪个 ADC（adc0, adc1, adc2, adc3, adc4...）
   - 告知使用者 BOM_Name_Target 的 DRDI 是 adcX
   - 去 D 的 .dws 文件确保 ADC 配置与 C 一致
   ↓
3. 如果未找到：
   - 检查 C 路径是否包含 tran_projects
   - 如果包含：在 C 的 .dts 文件中搜索 md_auxadc 配置
     - io-channels = <&pmic_adc (ADC_PURES_OPEN_MASK | AUXADC_VIN1)>
     - 告知使用者让使用者自己 check D 的配置
   - 如果不包含：直接告知使用者联系 RF 同事确认 DRDI 方式是 ADC 还是 GPIO
```

### ADC 编号识别
```xml
<adc0>
    <varName>ADC_FDD_RF_PARAMS_DYNAMIC_CUSTOM_CH</varName>
</adc0>
```
上述示例表示 DRDI 使用的是 adc0。

### DTS 文件查找
```dts
&md_auxadc {
    io-channels = <&pmic_adc (ADC_PURES_OPEN_MASK | AUXADC_VIN1)>;
};
```
如果找到此配置，说明 DRDI 使用 ADC 方式。

### DRDI 配置差异处理
| 情况 | 处理方式 |
|------|----------|
| C 和 D 的 ADC 编号一致 | 无需修改 |
| C 和 D 的 ADC 编号不一致 | 提示用户确认是否修改 |
| C 和 D 都未找到 DRDI 配置 | 提示用户联系 RF 同事确认 |

## 版本规范

### TOS16 之前版本
- 路径格式：`tran_projects/*/*/vendor/mediatek/proprietary/tools/dct/dws/<platform>`
- .dws 文件命名：`<bom_name>.dws`

### TOS16 及之后版本
- 路径格式：`vendor/mediatek/proprietary/tools/dct/dws/<platform>`
- .dws 文件命名：`<bom_name>.dws`

## 代码规范

### PowerShell 脚本规范
```powershell
# 变量命名：驼峰命名法
$targetDwsFile_C = $null

# 函数命名：动词开头
Function GetGpioConfig {
    param(
        [string]$content,
        [string]$gpioNum
    )
    # 函数体
}

# 注释规范
# 单行注释：说明功能
<# 
多行注释：详细说明
#>
```

### 正则表达式规范
```powershell
# 使用命名组提高可读性
$pattern = '(?<gpio>GPIO\d+).*MODE1\((?<mode>[^)]+)\)'
$match = [regex]::Match($content, $pattern)
$gpioNum = $match.Groups['gpio'].Value
$mode = $match.Groups['mode'].Value
```

## 参考资料

- [MediaTek GPIO Configuration Guide](https://www.mediatek.com/)
- [DCT Tool User Manual](https://www.mediatek.com/)
- [Android GPIO Configuration](https://source.android.com/devices/architecture/hidl/hidl)
