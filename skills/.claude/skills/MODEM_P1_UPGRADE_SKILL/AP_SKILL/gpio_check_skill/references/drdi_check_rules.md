# DRDI 检查参考规范

## DRDI 基本概念

### 什么是 DRDI
DRDI（Dynamic RF Parameters Dynamic Customization，射频参数动态定制）是一种用于在不同产品平台上动态配置射频参数的机制。它允许通过 ADC 或 GPIO 引脚来识别当前产品平台，从而加载对应的射频参数。

### DRDI 的作用
- 实现单一射频固件支持多个产品平台
- 通过硬件识别信号（ADC 电平或 GPIO 状态）自动选择正确的射频参数
- 提高射频固件的可重用性和灵活性

## DRDI 配置方式

### 方式一：ADC 方式
通过 ADC 采样获取平台识别电压，从而识别产品型号。

#### ADC 配置文件示例
```xml
<!-- .dws 文件中的 ADC 配置 -->
<adc0>
    <varName>ADC_FDD_RF_PARAMS_DYNAMIC_CUSTOM_CH</varName>
</adc0>
<adc1>
    <varName></varName>
</adc1>
<adc2>
    <varName></varName>
</adc2>
```

#### ADC 采样原理
```
平台识别电压 → ADC 采样 → 电压范围匹配 → 加载对应 RF 参数
     ↓
  ADC0 (e.g., 0.8V) → 产品 A
  ADC1 (e.g., 1.2V) → 产品 B
  ADC2 (e.g., 1.8V) → 产品 C
```

### 方式二：GPIO 方式
通过 GPIO 引脚的电平状态来识别产品型号。

#### GPIO 配置文件示例
```xml
<!-- .dws 文件中的 GPIO 配置 -->
<gpioXX>
    <def_mode>0</def_mode>
    <def_dir>IN</def_dir>
    <inpull_en>true</inpull_en>
</gpioXX>
```

### 方式三：DTS 配置方式
通过设备树文件配置平台识别。

#### DTS 配置示例
```dts
&md_auxadc {
    io-channels = <&pmic_adc (ADC_PURES_OPEN_MASK | AUXADC_VIN1)>;
};
```

## DRDI 识别流程

### 完整检查流程图
```
开始 DRDI 检查
    ↓
检查 C 的 .dws 文件中是否有 ADC_FDD_RF_PARAMS_DYNAMIC_CUSTOM_CH
    ↓
┌───┴───┐
↓       ↓
有      没有
↓       ↓
确定 ADC   检查 C 路径是否包含 tran_projects
编号      ↓
↓       ┌───┴───┐
去 D 的  ↓       ↓
.dws 确保  包含     不包含
配置一致  ↓       ↓
    ↓   查找 DTS   告知用户
    ↓   md_auxadc  联系 RF
    ↓       ↓       同事确认
    ↓   告知用户
    ↓   自行 check
    ↓   D 配置
    ↓
结束
```

## DRDI 常见问题

### 问题 1：ADC 编号不一致
**现象**：C 和 D 的 DRDI ADC 编号不一致

**原因**：
- 硬件设计变更
- 平台识别引脚更换
- 射频方案调整

**处理方式**：
1. 确认硬件设计是否变更
2. 如无变更，修改 D 的配置与 C 保持一致
3. 如有变更，联系射频团队确认

### 问题 2：找不到 DRDI 配置
**现象**：C 和 D 的 .dws 文件中都找不到 ADC_FDD_RF_PARAMS_DYNAMIC_CUSTOM_CH

**可能原因**：
- DRDI 使用 GPIO 方式
- DRDI 使用 DTS 方式
- 产品不支持 DRDI

**处理方式**：
1. 检查 .dts 文件中的 md_auxadc 配置
2. 联系射频同事确认 DRDI 方式
3. 检查 GPIO 配置

### 问题 3：DTS 文件路径问题
**现象**：找不到对应的 .dts 文件

**处理方式**：
1. 确认 C 路径的完整目录结构
2. 使用文件搜索工具查找 .dts 文件
3. 确认设备树文件命名规则

## DRDI 配置检查清单

### .dws 文件检查项
- [ ] 确认是否存在 ADC_FDD_RF_PARAMS_DYNAMIC_CUSTOM_CH
- [ ] 确认 ADC 编号（adc0, adc1, adc2...）
- [ ] 确认 ADC 配置项完整（varName 标签）
- [ ] 对比 C 和 D 的 ADC 编号是否一致

### DTS 文件检查项
- [ ] 确认是否存在 md_auxadc 节点
- [ ] 确认 io-channels 配置
- [ ] 确认 ADC_PURES_OPEN_MASK 或 AUXADC_VIN1 配置
- [ ] 对比 C 和 D 的 DTS 配置是否一致

### GPIO 检查项（如使用 GPIO 方式）
- [ ] 确认 DRDI GPIO 引脚编号
- [ ] 确认 def_mode 配置
- [ ] 确认 def_dir 配置（通常为 IN）
- [ ] 确认 inpull_en 配置

## 参考资料

### 相关文档
- MediaTek DRDI 设计规范
- Android HAL 射频配置文档
- 设备树 (DTS) 配置指南

### 关键词
- DRDI
- ADC_FDD_RF_PARAMS_DYNAMIC_CUSTOM_CH
- md_auxadc
- AUXADC_VIN1
- ADC_PURES_OPEN_MASK
- 射频参数动态定制