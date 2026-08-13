---
funcType: "AI自动化适配"
category: "驱动"
---
﻿---
name: vib-adapt-factory-cali
description: 检查并适配 Transsion/MTK 线性马达工模校准属性导入链路：确认公共 vibrator.mk 是否包含 ro.vendor.tran.midtest.lra.cali.min/max，并确认目标 projects/<project>/ProjectConfig.mk 是否开启 LRA 相关宏控。Use when 处理线性马达/LRA 工模校准、midtest 校准范围、ro.vendor.tran.midtest.lra.cali.min/max、TRAN_RICHTAP_SUPPORT、TRAN_VIB_LIB_NAME、vibrator.mk 或 ProjectConfig.mk 导入问题。
---

# Transsion 线性马达工模校准属性导入

## 适用范围

当需要检查某个项目是否已经导入线性马达工模校准属性，或需要适配项目使工模/产测能够读取 LRA 校准范围时，使用本 Skill。

典型源文件和目标文件：
- 公共属性来源：`odm_modules/common/vibrator/vibrator.mk`
- 项目宏控目标：`projects/<project>/ProjectConfig.mk`

## 预期属性

公共 `vibrator.mk` 应在线性马达使能条件块内导出工模校准范围：

```makefile
ifeq ($(strip $(TRAN_RICHTAP_SUPPORT)),yes)
# factory cali range
PRODUCT_ODM_PROPERTIES += ro.vendor.tran.midtest.lra.cali.min=1600
PRODUCT_ODM_PROPERTIES += ro.vendor.tran.midtest.lra.cali.max=1800
endif
```

以当前分支中的取值为准。用户未指定校准范围时，保持分支默认值，通常为 `1600` 和 `1800`。

Z 轴马达使用专用校准范围：

```makefile
PRODUCT_ODM_PROPERTIES += ro.vendor.tran.midtest.lra.cali.min=2150
PRODUCT_ODM_PROPERTIES += ro.vendor.tran.midtest.lra.cali.max=2450
```

## 工作流程

1. 确认目标项目。
   - 优先使用用户明确给出的项目名、文件路径、分支上下文或已打开的 `ProjectConfig.mk`。
   - 如果可能匹配多个项目配置，编辑前先让用户确认目标项目。

2. 检查公共 `vibrator.mk`。
   - 读取 `odm_modules/common/vibrator/vibrator.mk`。
   - 确认是否同时包含：
     - `ro.vendor.tran.midtest.lra.cali.min`
     - `ro.vendor.tran.midtest.lra.cali.max`
   - 确认这些属性是否受 `TRAN_RICHTAP_SUPPORT=yes` 条件控制。
   - 如果项目明确为 Z 轴马达，校准范围应检查为 `2150` 和 `2450`。
   - 如果公共文件缺少这些属性，先在现有线性马达 ODM 属性附近补充，再处理项目配置。

3. 检查目标 `ProjectConfig.mk`。
   - 搜索马达相关关键字：`VIB`、`vib`、`HAPTIC`、`haptic`、`RICHTAP`、`richtap`、`TRAN_VIB_LIB_NAME`、`CUSTOM_KERNEL_VIBRATOR`。
   - 确认项目是否已开启：

```makefile
TRAN_RICHTAP_SUPPORT = yes
TRAN_VIB_LIB_NAME = libtiktapvibrator
```

4. 缺少项目宏控时进行适配。
   - 将缺少的宏补到 `projects/<project>/ProjectConfig.mk`，不要在项目配置中重复添加 ODM 属性。
   - 如果已有 vibrator/haptic 硬件特性区域，优先放在该区域附近。
   - 如果没有相关区域，放在相近硬件特性宏附近，并保持改动最小。
   - 如果 `vibrator.mk` 或相邻项目配置使用了不同库名，沿用当前分支的实际库名。

5. 保守处理冲突。
   - 如果 `ProjectConfig.mk` 明确关闭马达支持，例如 `CUSTOM_KERNEL_VIBRATOR = no` 或 vibrator support 属性为 `0`，停止修改并报告冲突。
   - 如果项目使用非线性马达方案，未经确认不要强行添加 LRA 宏控。
   - 如果公共文件或不同分支之间的校准范围不一致，说明差异并询问使用哪组范围。

6. 修改后验证。
   - 重新读取或搜索已修改的 `ProjectConfig.mk`，确认没有重复或冲突的马达宏控。
   - 确认导入链路：`ProjectConfig.mk` 开启 `TRAN_RICHTAP_SUPPORT`，从而激活 `vibrator.mk` 并导出 `ro.vendor.tran.midtest.lra.cali.min/max`。
   - 如果有可用 lint，检查已编辑文件。

## 判断规则

- 如果 `vibrator.mk` 已包含两项校准属性，且 `ProjectConfig.mk` 已开启 `TRAN_RICHTAP_SUPPORT=yes`，结论为工模校准属性已导入。
- 如果 `vibrator.mk` 已包含属性，但 `ProjectConfig.mk` 缺少 LRA 宏控，将缺少的宏补到 `ProjectConfig.mk`。
- 如果 `vibrator.mk` 缺少校准属性，优先补公共属性，使所有已开启 LRA 的项目统一继承。
- 如果项目为 Z 轴马达，校准属性应使用 `min=2150`、`max=2450`；如果公共默认值仍为 `1600/1800`，需要确认是否存在项目级覆盖机制，不能直接按通用值判定已适配。
- 除非当前分支已有这种写法或用户明确要求，不要把 `ro.vendor.tran.midtest.lra.cali.min/max` 直接添加到每个项目配置中。

## 输出格式

用中文回复：

```markdown
结论：
- [已导入 / 已补充宏控 / 已补充公共属性 / 存在冲突需确认]

检查：
- `odm_modules/common/vibrator/vibrator.mk` 中校准属性状态
- `projects/<project>/ProjectConfig.mk` 中线性马达宏控状态

修改：
- 本次补充或确认的文件和关键内容

验证：
- 导入链路和冲突检查结果
```
