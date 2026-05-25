---
name: com-voice-ecc-emergency
description: "紧急拨号ECC异常分析: 覆盖紧急拨号ECC号码识别、云端/本地配置文件更新链路、拦截判定(MTK/QCOM/Unisoc blocker)、版本检查、MCCMNC刷新、BlockList更新等全链路的异常分析 | 紧急拨号/ECC/紧急呼叫/紧急号码/EmergencyNumber/emergency/112/110 | 当用户报告与「紧急拨号ECC异常分析」相关的日志分析需求时使用"
---

# 紧急拨号ECC异常分析

## 适用范围

本场景用于分析 ECC 号码识别、配置更新、拦截策略和紧急拨号建链链路。它既覆盖“号码是否应被识别为紧急号码”，也覆盖“识别后是否应允许拨出或被策略拦截”。

典型问题包括：

- 112/110/119/120 等号码识别错误。
- 应允许拨出的号码被误拦截。
- 应拦截的号码漏拦截。
- 云端或本地 ECC/BlockList 文件未生效。
- 已识别为 ECC，但紧急拨号建链失败。

## 不适用场景

- 普通通话拨号失败：优先 `com-voice-call-dialing`。
- SIM 不识别导致 MCC/MNC 缺失：先结合 `com-data-sim-recognition` 判断卡状态。
- 仅 UI 显示紧急呼叫按钮异常，无 ECC/Telephony 日志：只能定位到 UI 或证据不足。

## 前置条件

### 必需日志

- `bugreport*.txt`
- `radio-log*`
- `main_log*`
- `sys_log*`
- `mainlogcat-log*`
- `systemlogcat-log*`
- `0-android_main.log*`
- `0-android_system.log*`

## 分析步骤

```text
- [ ] 检查 ECC 更新触发
- [ ] 检查云端/本地配置版本
- [ ] 检查 MCC/MNC 刷新
- [ ] 检查 BlockList 更新和解析
- [ ] 检查 shouldBlock 判定
- [ ] 检查紧急拨号建链
```

---

## 分析前最小证据集

优先确认：

- 拨打号码、国家/地区、运营商、SIM 有卡/无卡/漫游状态。
- 现象是误拦截、漏拦截、无法识别，还是识别后建链失败。
- 问题时间点，至少到分钟级。
- `radio-log*`、`main_log*`、`sys_log*` 是否覆盖配置更新和拨号时刻。
- 平台类型：MTK/QCOM/UNISOC，因为 blocker 实现不同。

若当前日志只含 I 级及以上，不能因缺少 D 级解析细节直接判定配置异常；先建议 `adb shell setprop persist.log.tag D` 复测抓取，再用现有 I/W/E 证据保守分析。

---

## 快速命中判断

出现以下信号可认为命中 ECC 场景：

- `EmergencyNumberTracker.*mTranIntentReceiver.*intent`
- `TranEmergencyNumberComponentImpl.*updateEmergencyNumberFromTran.*start update`
- `TranMtkEccVersionChecker.*checkIfUseCloudFile`
- `TranEccMccMncTool.*updateMccMnc`
- `TranMtkEccblocker.*updateBlockList`
- `TranMtkEccblocker.*shouldBlock` / `TranQcomEccBlocker.*shouldBlock` / `TranUniEccUtils.*shouldBlock`
- `EmergencyNumberTracker.*Search results`
- `Telephony.*placeEmergencyConnection` / `startEmergencyCall`

---

## 正常链路参考

正常 ECC 链路通常包含：

1. 卡状态、网络状态或配置广播触发 ECC 更新链路。
2. 版本检查决定使用云端或本地 ECC/BlockList 文件。
3. MCC/MNC 和 countryIso 刷新成功。
4. BlockList 文件存在并解析成功，生成当前地区和卡状态对应的号码集合。
5. 拨打号码时，EmergencyNumberTracker 判断是否在 ECC 集合中。
6. blocker 做出 shouldBlock 判定，结果应与配置和地区预期一致。
7. 如果允许拨出，Telephony 进入 `placeEmergencyConnection` / `startEmergencyCall`，Radio/Modem 就绪并完成建链。

---

## 标准分析流程

### Step 1：检查 ECC 更新触发

- **目标**：确认配置更新链路是否被触发。
- **关键证据**：`mTranIntentReceiver.*intent`、`updateEmergencyNumberFromTran.*start update`。
- **判断**：无触发时，检查静态配置、历史缓存或拨号阶段识别证据。

### Step 2：检查云端/本地配置版本

- **目标**：确认选择的配置文件来源和版本解析是否正常。
- **关键证据**：`checkIfUseCloudFile`、`no version file`、`wrong parser`。
- **判断**：版本文件缺失或解析错误，偏配置投放、文件路径、权限或格式问题。

### Step 3：检查 MCC/MNC 刷新

- **目标**：确认地区信息是否正确，避免选错 ECC 集合。
- **关键证据**：`updateMccMnc`、`updateCountryIso`、`empty mcc`。
- **判断**：MCC 为空时，优先检查 SIM 状态、运营商信息获取、countryIso 缓存更新。

### Step 4：检查 BlockList 更新和解析

- **目标**：确认文件存在、被正确选择并成功解析。
- **关键证据**：`updateBlockList`、`use cloud file`、`file not exist`、`No valid ecc`、`ecc with card`。
- **判断**：文件不存在偏投放/路径/权限；解析失败偏格式/版本不兼容。

### Step 5：检查 shouldBlock 判定

- **目标**：判断误拦截、漏拦截或正常拦截。
- **关键证据**：`shouldBlock`、`Search results`、号码是否在 ECC/BlockList 集合中。
- **判断**：误拦截是号码不应被拦截但 shouldBlock 为 true；漏拦截是号码应被拦截但 shouldBlock 为 false 或未执行。

### Step 6：检查紧急拨号建链

- **目标**：若识别和拦截正常，继续确认拨号是否建链成功。
- **关键证据**：`placeEmergencyConnection`、`startEmergencyCall`、`failed to turn on radio`、`dialing canceled`。
- **判断**：识别正常但建链失败时，偏 Radio/Modem/IMS/CS 域选择，而不是 ECC 配置。

---

## 常见断点地图

| 断点 | 典型证据 | 建议归因方向 |
|---|---|---|
| 版本文件缺失 | `no version file` | 云端/本地文件投放、路径、权限 |
| 解析器不兼容 | `wrong parser` / `No valid ecc` | 文件格式或版本兼容性 |
| MCC 为空 | `empty mcc` | SIM 状态、MCCMNC 获取、countryIso 缓存 |
| BlockList 未生效 | `file not exist` / 无 updateBlockList | 配置下发、触发时机、文件挂载 |
| 拦截判断错误 | shouldBlock 与预期不一致 | 地区分支、卡状态分支、号码归一化 |
| 识别正常但拨号失败 | `failed to turn on radio` | Radio/Modem/IMS/CS 建链问题 |

---

## 输出要求

- 先说明问题属于：识别异常、配置更新异常、拦截策略异常、还是拨号建链异常。
- 误拦截/漏拦截必须引用号码、MCC/MNC、BlockList 或 shouldBlock 证据。
- 建链失败必须区分 ECC 配置问题和 Radio/Modem 问题。
- 最多给 3 个可能原因和 3 条下一步建议。

---

## 证据约束

- 没有号码、地区、SIM 状态信息时，不能判断误拦截或漏拦截。
- 没有 MCC/MNC 刷新证据时，不能确认地区配置已生效。
- 没有 BlockList 解析结果时，不能确认当前号码集合正确。
- 没有 shouldBlock 证据时，不能判断拦截策略是否执行。
- 已识别为 ECC 但拨号失败时，应区分配置/拦截问题和 Radio/Modem 建链问题。
