---
name: com-data-sim-recognition
description: "开机SIM卡识别异常分析: 覆盖开机SIM卡识别全流程：UiccController创建与RADIO_AVAILABLE接收、ICC状态获取、UiccCardApplication创建与通知、UiccProfile外部状态设置、ACTION_SIM_STATE_CHANGED广播等 | SIM卡/SIM/识别/无SIM/不识卡/检测不到卡/SIM卡识别/UiccController | 当用户报告与「开机SIM卡识别异常分析」相关的日志分析需求时使用"
---

# 开机SIM卡识别异常分析

## 适用范围

本场景用于分析从 Telephony 初始化到上层 SIM READY 广播的完整链路，重点定位断点发生在：Radio 就绪、ICC 状态查询、卡应用创建、UiccProfile 外部状态更新，还是上层广播同步。

典型问题包括：

- 开机后显示无 SIM 或检测不到卡。
- 插卡后长期停留在 UNKNOWN / NOT_READY。
- 底层返回 `CARDSTATE_PRESENT`，但上层未显示 READY。
- 多卡场景中某个 slot/phoneId 状态异常。

## 不适用场景

- SIM 已识别，但无法注册网络、无服务、数据不可用：优先转蜂窝网络/注册/数据连接专题。
- SIM 电话本联系人写入失败：优先 `com-data-sim-contact-add`。
- 仅 UI 显示异常且无 Telephony/UICC 证据：只能定位到上层状态同步或日志不足。

## 前置条件

### 必需日志

- `bugreport*.txt`
- `radio-log*`
- `main_log*`
- `events-log*`
- `mainlogcat-log*`
- `sys_log*`
- `systemlogcat-log*`
- `0-android_main.log*`
- `0-android_system.log*`

## 分析步骤

```text
- [ ] 检查 UiccController 初始化与 Radio 就绪
- [ ] 检查 ICC 状态查询结果
- [ ] 检查 UiccCardApplication READY
- [ ] 检查 UiccProfile 外部状态
- [ ] 检查 SIM_STATE 广播
```

---

## 分析前最小证据集

优先确认：

- 问题发生时间点，至少到分钟级。
- 机型、版本、平台和单卡/双卡状态。
- 目标 `phoneId` / `slotId` / `subId`。
- 是否冷启动、热插拔、飞行模式恢复、重启后首次识别。
- `radio-log*`、`main_log*`、`events-log*`、`systemlogcat-log*` 是否覆盖问题时间。

如果日志只包含 I 级及以上，不能因缺少 D 级 UICC 细节直接判错；应先建议复测执行 `adb shell setprop persist.log.tag D` 后重新抓取，再基于现有 I/W/E 证据保守分析。

---

## 快速命中判断

出现以下任一组信号，通常可认为进入 SIM 识别链路：

- `UiccController.*Creating UiccController`
- `UiccController.*Received RADIO_AVAILABLE` / `EVENT_RADIO_AVAILABLE` / `EVENT_RADIO_ON`
- `UiccController.*getIccCardStatus` / `GET_ICC_STATUS_DONE`
- `CARDSTATE_PRESENT` / `CARDSTATE_ABSENT` / `CARDSTATE_ERROR`
- `UiccCardApplication.*APPSTATE_READY`
- `UiccProfile.*setExternalState.*READY`
- `ACTION_SIM_STATE_CHANGED.*READY`

---

## 正常链路参考

正常开机识卡链路应包含以下阶段：

1. Telephony 初始化，`UiccController` 创建成功。
2. Radio 上报可用，收到 `RADIO_AVAILABLE` / `EVENT_RADIO_ON`。
3. Framework 调用 `getIccCardStatus` 查询 ICC 状态。
4. `onGetIccCardStatusDone` 返回卡状态：有卡为 `CARDSTATE_PRESENT`，无卡为 `CARDSTATE_ABSENT`。
5. 有卡时创建 `UiccCardApplication`，识别 SIM/USIM 应用类型。
6. 卡应用进入 `APPSTATE_READY`，`IccRecords` 创建并通知 READY registrant。
7. `UiccProfile` 外部状态设置为 READY。
8. 发出 `ACTION_SIM_STATE_CHANGED READY` 广播，上层状态同步完成。

飞书正常案例只能作为链路阶段参考，不能把其中的 READY 日志当作当前问题的证据。

---

## 标准分析流程

### Step 1：检查 UiccController 初始化与 Radio 就绪

- **目标**：确认 SIM 识别链路是否真正开始。
- **关键证据**：`Creating UiccController`、`RADIO_AVAILABLE`、`EVENT_RADIO_ON`。
- **判断**：缺少 UiccController 创建偏 Telephony 初始化或日志窗口问题；缺少 Radio available 偏 Radio/Modem 开机就绪异常。

### Step 2：检查 ICC 状态查询结果

- **目标**：确认卡状态是 PRESENT、ABSENT 还是 ERROR。
- **关键证据**：`getIccCardStatus`、`onGetIccCardStatusDone`、`CARDSTATE_*`。
- **判断**：`CARDSTATE_PRESENT` 进入卡应用创建和上层状态同步检查；`CARDSTATE_ABSENT` 优先考虑物理卡、卡槽、Modem 返回或插卡状态；`CARDSTATE_ERROR` 优先考虑卡错误、读卡失败、Modem/RIL 返回异常。

### Step 3：检查 UiccCardApplication READY

- **目标**：确认卡应用是否创建并进入 READY。
- **关键证据**：`Creating UiccApp`、`APPTYPE_USIM`、`APPSTATE_READY`、`Notifying READY`。
- **判断**：PRESENT 后没有应用创建偏 UICC 应用初始化异常；应用创建但不 READY 偏 PIN、卡应用状态、记录加载或卡响应问题。

### Step 4：检查 UiccProfile 外部状态

- **目标**：确认上层可见状态是否同步为 READY。
- **关键证据**：`UiccProfile.*setExternalState`、`mExternalState.*READY`。
- **判断**：底层 READY 但外部状态未 READY，偏 Profile 状态机或上层同步异常。

### Step 5：检查 SIM_STATE 广播

- **目标**：确认 READY 是否通知到上层。
- **关键证据**：`ACTION_SIM_STATE_CHANGED.*READY`。
- **判断**：Profile READY 但广播缺失，偏广播发送或上层状态通知异常；广播已发但 UI 无变化，偏 UI/Settings/状态缓存刷新问题。

---

## 常见断点地图

| 断点 | 典型证据 | 建议归因方向 |
|---|---|---|
| Telephony 未初始化 | 无 `Creating UiccController` | Telephony 服务启动或日志窗口问题 |
| Radio 未就绪 | 无 `RADIO_AVAILABLE` | Radio/Modem 开机就绪异常 |
| ICC 查询无结果 | 无 `GET_ICC_STATUS_DONE` | RIL/Modem 卡状态查询异常 |
| 返回 ABSENT/ERROR | `CARDSTATE_ABSENT` / `CARDSTATE_ERROR` | 物理卡、卡槽、Modem 返回、卡错误 |
| App 未 READY | 无 `APPSTATE_READY` | UiccCardApplication 或卡应用初始化异常 |
| 广播缺失 | 无 `ACTION_SIM_STATE_CHANGED READY` | UiccProfile 到上层广播同步异常 |

---

## 输出要求

- 先判断当前能定位到哪一层：Radio、ICC 状态、UiccApp、UiccProfile、广播或 UI。
- 最多给 3 个可能原因，按可能性排序。
- 每个原因必须引用当前日志证据；没有证据只能列为待验证。
- 如果缺少 D 级日志，先建议 `adb shell setprop persist.log.tag D` 复测，再基于现有 I 级日志给保守结论。

---

## 证据约束

- 没有 Radio available 证据时，不能判断 SIM 识别链路已经开始。
- 没有 ICC status 结果时，不能确认卡是 absent、present 还是 error。
- 没有 UiccProfile READY 或 READY 广播时，不能确认上层已经识卡成功。
- 必须区分“底层未识别卡”和“底层已识别但上层状态未同步”。
