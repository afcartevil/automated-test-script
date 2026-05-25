---
name: near-bt-switch
description: "蓝牙开关异常分析: 蓝牙主开关打开或关闭过程中出现的异常分析，包括开关操作、状态机转换、广播事件分发、适配器接口调用、系统服务绑定等 | 蓝牙开关/打开蓝牙/关闭蓝牙/蓝牙无法打开/蓝牙无法关闭/蓝牙开不了/bluetooth switch/BT开关 | 当用户报告与「蓝牙开关异常分析」相关的日志分析需求时使用"
---

# 蓝牙开关异常分析

## 适用范围

本场景用于分析蓝牙主开关从用户操作到 AdapterState 状态迁移的完整链路，重点定位问题在 UI 入口、BluetoothAdapter 调用、BluetoothManagerService 绑定、蓝牙服务进程，还是状态广播/UI 刷新。

典型问题包括：

- 点击蓝牙开关后无反应。
- 开关一直停在打开中/关闭中。
- 蓝牙实际已开但设置页仍显示关闭，或反之。
- `Wait for STATE_ON/OFF timeout`、`Impossible transition`、service disconnected。

## 不适用场景

- 蓝牙已打开但设备无法配对/连接：优先 `near-bt-device-connect`。
- 蓝牙文件传输失败：优先 `near-bt-opp-transfer`。
- 仅 Settings UI 卡顿但系统蓝牙状态正常：应定位 UI 刷新或设置页问题。

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
- [ ] 检查开关入口
- [ ] 检查 Adapter enable/disable 调用
- [ ] 检查服务绑定
- [ ] 检查 AdapterState 状态机
- [ ] 检查广播和 UI 刷新
```

---

## 分析前最小证据集

优先确认：

- 用户是打开还是关闭蓝牙。
- 操作入口：设置页、快捷开关、其他应用调用 API。
- 问题时间点和持续时间。
- 是否多用户/开机首次打开/飞行模式联动。
- `mainlogcat-log*`、`sys_log*`、`systemlogcat-log*` 是否覆盖操作前后。

如果当前日志只有 I 级及以上，不能因缺少 D 级状态机细节直接判错；先建议 `adb shell setprop persist.log.tag D` 复测，再基于现有 I/W/E 证据分析。

---

## 快速命中判断

出现以下信号可认为命中蓝牙开关链路：

- `SETTING_BT_TAG.*onPreferenceChange`
- `BluetoothAdapter.*enable()` / `disable()`
- `BluetoothSystemServer.*BluetoothManagerService`
- `BluetoothManagerService.*MESSAGE_TIMEOUT_BIND`
- `AdapterState.*BLE_TURNING_ON` / `TURNING_ON` / `ON : entered`
- `AdapterState.*TURNING_OFF` / `OFF : entered`
- `BluetoothEventManager:`

---

## 正常链路参考

正常打开蓝牙：

1. 用户在设置页或快捷开关触发开关动作。
2. `BluetoothAdapter.enable()` 被调用。
3. `BluetoothManagerService` 绑定并启动蓝牙服务。
4. `AdapterState` 按 `BLE_TURNING_ON -> BLE_ON -> TURNING_ON -> ON` 转换。
5. 状态广播分发，Settings/UI 同步刷新。

正常关闭蓝牙：

1. 用户触发关闭动作。
2. `BluetoothAdapter.disable()` 被调用。
3. `AdapterState` 按 `TURNING_OFF -> BLE_TURNING_OFF -> OFF` 转换。
4. 服务和 UI 状态清理完成。

---

## 标准分析流程

### Step 1：检查开关入口

- **目标**：确认用户动作是否进入设置/框架。
- **关键证据**：`SETTING_BT_TAG.*onPreferenceChange`。
- **判断**：无入口日志时，优先怀疑 UI 入口、操作时间窗口或日志缺失。

### Step 2：检查 Adapter enable/disable 调用

- **目标**：确认 Framework API 是否被调用。
- **关键证据**：`BluetoothAdapter.*enable()` / `disable()`。
- **判断**：入口存在但 Adapter 调用缺失，偏 Settings 到 Framework 调用链路。

### Step 3：检查服务绑定

- **目标**：确认 BluetoothManagerService 是否成功绑定/启动服务。
- **关键证据**：`BluetoothSystemServer.*BluetoothManagerService`、`MESSAGE_TIMEOUT_BIND`、`Fail to bind`、`MESSAGE_BLUETOOTH_SERVICE_DISCONNECTED`。
- **判断**：绑定超时或服务断开，偏蓝牙服务进程/组件声明/系统服务绑定异常。

### Step 4：检查 AdapterState 状态机

- **目标**：确认状态转换完整且顺序合理。
- **关键证据**：`BLE_TURNING_ON`、`ON : entered`、`TURNING_OFF`、`OFF : entered`。
- **判断**：状态机卡住或 `Impossible transition` 是主要异常证据。

### Step 5：检查广播和 UI 刷新

- **目标**：确认状态已同步到上层。
- **关键证据**：`BluetoothEventManager:`、状态变更广播。
- **判断**：底层 ON/OFF 已完成但 UI 不刷新，偏广播分发或设置页缓存。

---

## 常见断点地图

| 断点 | 典型证据 | 建议归因方向 |
|---|---|---|
| 开关入口缺失 | 无 `onPreferenceChange` | UI/设置页入口或时间窗口问题 |
| Adapter 调用缺失 | 无 `enable()` / `disable()` | Framework API 调用未到达 |
| 服务绑定失败 | `MESSAGE_TIMEOUT_BIND` / `Fail to bind` | 蓝牙服务启动或绑定异常 |
| 状态机卡住 | `Impossible transition` / timeout | AdapterState 状态机异常 |
| UI 不刷新 | 已 ON/OFF 但 EventManager/UI 异常 | 广播分发或 Settings 刷新问题 |

---

## 输出要求

- 先判断问题卡在哪一层：入口、Adapter 调用、服务绑定、状态机、广播/UI。
- 不要只凭 UI 现象判断底层蓝牙异常，必须引用状态机或服务证据。
- 如果只有 I 级日志，先建议打开 D 级日志复测，再给现有证据下的保守结论。

---

## 证据约束

- 没有用户开关动作时，不能确认问题发生在开关流程。
- 没有 AdapterState 状态迁移时，不能判断蓝牙协议栈已进入开关状态机。
- 底层状态机正常但 UI 异常时，优先怀疑广播/UI 刷新。
- 正常案例只用于对比链路完整性，不是当前问题事实。
