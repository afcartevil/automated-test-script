# DRDI 检查决策树

## 决策流程

```
开始
  ↓
C 的 .dws 中是否找到 ADC_FDD_RF_PARAMS_DYNAMIC_CUSTOM_CH？
  ↓
┌─────────────┴─────────────┐
↓                           ↓
YES                         NO
↓                           ↓
确定是哪个 ADC               C 路径是否包含 tran_projects？
(adc0/1/2/3/4)               ↓
↓                     ┌─────┴─────┐
↓                     ↓           ↓
↓                    YES          NO
↓                     ↓           ↓
↓              查找 .dts 文件     联系 RF 同事
↓              md_auxadc          确认 DRDI 方式
↓                     ↓           (ADC 或 GPIO)
↓
D 的 .dws 中        告知用户
ADC 编号是否一致？  自行 check
↓               D 的配置
┌─────┴─────┐
↓           ↓
一致       不一致
↓           ↓
无需       确认是否
修改       修改为
           与 C 一致
```

## DRDI 配置方式速查表

| 配置方式 | 查找位置 | 查找内容 | 处理方式 |
|----------|----------|----------|----------|
| ADC 方式 | C 的 .dws | `ADC_FDD_RF_PARAMS_DYNAMIC_CUSTOM_CH` | 告知用户 DRDI 是 adcX |
| DTS 方式 | C 的 .dts | `md_auxadc` + `ADC_PURES_OPEN_MASK` | 告知用户自行 check D |
| GPIO 方式 | - | - | 联系 RF 同事确认 |

## 用户提示语模板

### 情况 1：在 .dws 中找到 DRDI
```
【DRDI 检查结果】
- DRDI 配置方式：ADC
- DRDI 编号：adc{0/1/2/3/4}
- 升级前（C）和升级后（D）的 ADC 编号：{一致/不一致}
- 处理建议：{无需修改/请确认是否修改为与升级前一致}
```

### 情况 2：在 .dts 中找到 DRDI
```
【DRDI 检查结果】
- DRDI 配置方式：DTS (md_auxadc)
- DTS 文件路径：{找到的 dts 文件路径}
- 处理建议：请自行检查目标路径 D 的 DRDI 配置是否与路径 C 一致
```

### 情况 3：未找到 DRDI 配置
```
【DRDI 检查结果】
- DRDI 配置方式：未知
- 处理建议：请联系 RF 同事确认 DRDI 的配置方式是 ADC 还是 GPIO
```

## 快速检查命令

### 检查 .dws 文件中的 DRDI 配置
```powershell
# 搜索 ADC_FDD_RF_PARAMS_DYNAMIC_CUSTOM_CH
Select-String -Path "*.dws" -Pattern "ADC_FDD_RF_PARAMS_DYNAMIC_CUSTOM_CH"

# 提取 ADC 编号
$content = Get-Content -Path "cm7_h781.dws" -Raw
$match = [regex]::Match($content, '<adc(\d+)>([\s\S]*?)varName>ADC_FDD_RF_PARAMS_DYNAMIC_CUSTOM_CH</varName>')
if ($match.Success) {
    $adcNum = $match.Groups[1].Value
    Write-Output "DRDI 使用的是 adc$adcNum"
}
```

### 检查 .dts 文件中的 md_auxadc 配置
```powershell
# 搜索 md_auxadc
Select-String -Path "*.dts" -Pattern "md_auxadc" -Context 2,2

# 搜索 ADC_PURES_OPEN_MASK 或 AUXADC_VIN1
Select-String -Path "*.dts" -Pattern "ADC_PURES_OPEN_MASK|AUXADC_VIN1"
```