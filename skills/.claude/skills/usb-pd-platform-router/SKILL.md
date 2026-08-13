---
name: usb-pd-platform-router
description: “USB-PD平台路由: 对USB Type-C/PD问题做平台级入口分流，区分Qualcomm ADSP架构与MediaTek tcpc/pd协议栈 | USB/PD/TypeC/插拔/协商/Qualcomm/MTK | 当用户只描述USB/PD/插拔/协商异常但未明确平台或主域时使用——本skill为路由入口”
funcType: "AI故障分析"
category: "驱动"
---

# USB PD 平台入口分流

## 作用

这是入口 skill，只做平台判定与首次分流，不替代领域 skill 深挖。
先判平台，再下钻领域；若平台不明，必须停止并反问，不允许继续分析。

目标分流：
- Qualcomm：`qualcomm-adsp-usb-pd-analysis`
- MediaTek：`mediatek-pd-typec-protocol-6-12`

## 平台判定

按以下顺序严格执行：
1. **用户提示词直判**
2. **日志锚点判定**
3. **仍不确定则停止并反问**

### 1) 用户提示词直判

#### 直判为 Qualcomm（命中任一即可）
- `高通` / `Qualcomm`
- `ADSP`
- `battman`
- `pmic_glink`
- `UCSI glink`
- `PmicTccPlatform`

#### 直判为 MediaTek（命中任一即可）
- `MTK` / `MediaTek`
- `kernel_device_modules-6.12`
- `mtu3`
- `ssusb`
- `tcpc`（且上下文为 MTK 内核栈）

### 2) 日志锚点判定

#### 判定为 Qualcomm（命中任一线索）

命中以下任一线索即可优先判定：
- `ADSP`
- `battman/usbtypec`
- `LPM` / `DPM` / `PPM`
- `pmic_glink`
- `PmicTccPlatform`
- `TCPCI alert` 由 ADSP 固件线程消费

进入：
- `qualcomm-adsp-usb-pd-analysis`

#### 判定为 MediaTek（命中任一线索）

命中以下任一线索即可优先判定：
- `tcpc`
- `tcpci_alert`
- `pd_policy_engine`
- `ps_change`
- `CC_ALERT`
- `TCPC-TYPEC`
- `kernel_device_modules-6.12/drivers/misc/mediatek/typec/tcpc`

进入：
- `mediatek-pd-typec-protocol-6-12`

### 3) 无法判定时（强制停止）

若 1) 和 2) 都无法给出明确平台，**必须停止深挖并反问用户**：
- `当前日志不足以判定平台。请确认这次要按 MTK 还是高通路径分析？`
- 在用户确认前，不进入任何 Qualcomm/MTK 专项 skill。

## 不确定时的最小确认项（仅用于反问）

优先向用户确认：
1. 问题代码主要在 `ADSP firmware` 还是 `kernel tcpc`
2. 是否存在 `LPM/DPM/PPM/pmic_glink`
3. 是否从 `tcpci_alert()` 开始追还是从 `PmicTccPlatform_*IRQ.c` 开始追

## 输出模板

```markdown
## 平台判定
- 平台：Qualcomm / MediaTek / Unknown
- 依据：<keywords or file path>

## 首次分流
- 主 skill：<skill name>
- 原因：<1-2 行>

## 平台不明处理
- 动作：停止深挖并反问
- 反问：当前日志不足以判定平台。请确认按 MTK 还是高通路径分析？

## 下一步入口
- 入口文件：<path>
- 起始函数：<function>
```

## 约束

- 平台未确认前，不要混用 Qualcomm `LPM/DPM/PPM` 术语与 MTK `tcpc/pd_policy_engine` 术语
- 若已明确是 Qualcomm ADSP，直接转入 `qualcomm-adsp-usb-pd-analysis`
- 若已明确是 MTK 6.12，直接转入 `mediatek-pd-typec-protocol-6-12`
- 若平台不明，必须停止并反问用户，禁止“先假设平台继续分析”
