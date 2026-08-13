---
name: near-bt-device-connect
description: "蓝牙设备连接配对异常分析: 蓝牙设备配对、连接、Profile调度过程中出现的异常分析，包括配对状态机、Profile连接、设备列表刷新等 | 蓝牙配对/蓝牙连接/配对失败/连接失败/bluetooth pairing/bluetooth connect/BT连接/耳机连接 | 当用户报告与「蓝牙设备连接配对异常分析」相关的日志分析需求时使用"
funcType: "AI故障分析"
category: "通信"
---

# 蓝牙设备连接配对异常分析

## 适用范围

本场景用于分析蓝牙设备从扫描列表点击、bonding、配对弹窗、Profile 连接到 UI 刷新的完整链路，重点区分“配对失败”和“已配对后 Profile 连接失败”。

典型问题包括：

- 点击设备后无法配对。
- PIN/确认弹窗不出现或确认后失败。
- 已 bonded 但耳机/车机/手表无法连接。
- A2DP/HFP/LE Audio 等 Profile 连接超时。
- 设备已连接但设置页列表不刷新。

## 不适用场景

- 蓝牙主开关打不开或关闭异常：优先 `near-bt-switch`。
- OPP 文件传输失败：优先 `near-bt-opp-transfer`。
- 只涉及音频路由或媒体播放无声：需要音频/Profile 专题结合分析。

## 前置条件

### 必需日志

- `bugreport*.txt`
- `mainlogcat-log*`
- `main_log*`
- `sys_log*`
- `systemlogcat-log*`
- `0-android_main.log*`
- `0-android_system.log*`

## 分析步骤

```text
- [ ] 检查点击和配对入口
- [ ] 检查 bond 状态机
- [ ] 检查配对弹窗和用户确认
- [ ] 检查 Profile 连接
- [ ] 检查设备列表刷新
```

---

## 分析前最小证据集

优先确认：

- 目标设备类型、名称、MAC 是否可用。
- 是首次配对还是已配对后重连。
- 发生时间点、用户是否确认 PIN/弹窗。
- 目标 Profile：A2DP、HFP、HID、LE Audio、PBAP 等。
- `mainlogcat-log*`、`sys_log*`、`systemlogcat-log*` 覆盖点击前后。

若当前日志只有 I 级及以上，不能因缺少 D 级 Profile 细节直接判错；先建议 `adb shell setprop persist.log.tag D` 复测，再基于现有 I/W/E 证据分析。

---

## 快速命中判断

出现以下信号可认为命中配对/连接链路：

- `BluetoothDashboardFrag.*onPreferenceTreeClick`
- `BluetoothBondStateMachine.*BONDING_STATE_CHANGE`
- `BluetoothBondStateMachine.*sendDisplayPinIntent`
- `BTPairingController.*Pairing dialog accepted`
- `CachedBluetoothDevice.*connect CachedBluetoothDevice`
- `BluetoothAdapterService.*connectEnabledProfiles`
- `CachedBluetoothDevice.*onProfileStateChanged`
- `SavedBluetoothDeviceUpdater.*update, matched cachedDevice`

---

## 正常链路参考

正常配对/连接链路应包含：

1. 用户在蓝牙设备列表点击目标设备。
2. 设备进入 bonding 流程，`BluetoothBondStateMachine` 发生状态迁移。
3. 如需 PIN/确认码，系统弹出 pairing dialog，用户确认。
4. bond 成功后进入 bonded 状态，缓存设备对象刷新。
5. 连接阶段调用 `connectEnabledProfiles` 或 `CachedBluetoothDevice.connect`。
6. 关键 Profile 状态从 connecting 进入 connected。
7. UI 列表刷新，目标设备显示已连接或对应 Profile 已连接。

---

## 标准分析流程

### Step 1：检查点击和配对入口

- **目标**：确认用户点击目标设备并进入配对/连接流程。
- **关键证据**：`BluetoothDashboardFrag.*onPreferenceTreeClick`。
- **判断**：缺少入口日志时，不能确认当前问题是配对/连接链路异常。

### Step 2：检查 bond 状态机

- **目标**：确认 pairing 状态从 BONDING 到 BONDED，或明确失败。
- **关键证据**：`BluetoothBondStateMachine.*BONDING_STATE_CHANGE`。
- **判断**：`not bonding`、`Incorrect pairing type` 指向配对状态机或弹窗确认异常。

### Step 3：检查配对弹窗和用户确认

- **目标**：确认 PIN/确认码流程是否完成。
- **关键证据**：`sendDisplayPinIntent`、`Pairing dialog accepted`、`setPin`、`setPairingConfirmation`。
- **判断**：弹窗出现但无 accepted，优先检查用户确认、弹窗显示、权限或 UI 被覆盖。

### Step 4：检查 Profile 连接

- **目标**：确认已配对设备的 Profile 是否连接成功。
- **关键证据**：`connectEnabledProfiles`、`CachedBluetoothDevice.*connect`、`onProfileStateChanged`。
- **判断**：bonded 后 Profile 失败不等于配对失败，应单独归因 Profile 服务、远端设备或协议连接。

### Step 5：检查设备列表刷新

- **目标**：确认 UI 是否匹配连接状态。
- **关键证据**：`SavedBluetoothDeviceUpdater.*update, matched cachedDevice`。
- **判断**：Profile 已 connected 但列表未刷新，偏 Settings 缓存设备/Preference 更新问题。

---

## 常见断点地图

| 断点 | 典型证据 | 建议归因方向 |
|---|---|---|
| 点击入口缺失 | 无 `onPreferenceTreeClick` | UI 入口或时间窗口问题 |
| bond 状态机异常 | `not bonding` / `Incorrect pairing type` | 配对状态机、PIN/确认流程 |
| 用户确认缺失 | 有弹窗但无 accepted | 弹窗显示、用户确认、权限 |
| Profile 连接失败 | `Failed to connect profile` / timeout | Profile 服务、远端设备、协议栈 |
| UI 刷新异常 | connected 后列表不更新 | Settings 缓存设备/Preference 刷新 |

---

## 输出要求

- 先明确当前是“配对阶段”还是“已配对后的 Profile 连接阶段”。
- 每个原因必须引用目标设备、bond 状态或 Profile 状态证据。
- Profile 失败不能直接等同于配对失败。
- 建议动作优先包含：复测抓 D 级日志、确认目标设备类型/Profile、删除配对后重新配对对比。

---

## 证据约束

- 没有目标设备点击或 createBond 证据时，不能确认进入配对流程。
- 没有 bond 状态变化时，不能判断配对状态机异常。
- Profile 连接失败不等于配对失败，必须区分 pairing 和 profile connect。
- 正常案例只用于对比链路完整性，不是当前问题事实。
