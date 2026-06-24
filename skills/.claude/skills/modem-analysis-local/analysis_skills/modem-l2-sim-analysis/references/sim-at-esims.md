# AT+ESIMS 命令完整参考

## 命令格式

```
+ESIMS:<sim_inserted_status>,<cause>
```

## 参数定义

### <sim_inserted_status>: integer
- `0` - SIM not presented（SIM 卡未插入）
- `1` - SIM presented（SIM 卡已插入）

### <cause>: integer（完整状态码表）

| 状态码 | 宏定义 | 说明 |
|--------|--------|------|
| 0 | SIM_CARD_REMOVED | 卡移除 |
| 1 | SIM_ACCESS_ERROR | 访问错误，不识卡 |
| 2 | SIM_REFRESH | SIM Refresh |
| 3 | SIM_REFRESH_POWER_OFF | SIM Refresh 下电 |
| 4 | SIM_PUK1 | PUK1 锁定 |
| 5 | SIM_ACCESS_PROFILE_ON | SIM Access Profile 开启 |
| 6 | SIM_ACCESS_PROFILE_OFF | SIM Access Profile 关闭 |
| 7 | DUALSIM_DISCONNECTED | 双卡断开 |
| 8 | DUALSIM_CONNECTED | 双卡连接 |
| 9 | SIM_VSIM_ON | 虚拟 SIM 开启 |
| 10 | SIM_VSIM_OFF | 虚拟 SIM 关闭 |
| 11 | SIM_PLUG_OUT | 拔卡 |
| 12 | SIM_PLUG_IN | 插卡 |
| 13 | SIM_RECOVERY_START | 救卡开始（仅在第一次 full recovery 启动时上报） |
| 14 | SIM_RECOVERY_END | 救卡成功（仅在 full recovery 成功时上报） |
| 15 | SIM_IMEI_LOCK_FAIL | IMEI 锁校验失败 |
| 16 | SIM_OP09_LOCK_FAIL | OP09 锁校验失败 |
| 17 | SIM_CARD_TECHNICAL_PROBLEM | SIM 卡技术问题 |
| 18 | SIM_POWEROFF_BY_L4 | L4 层主动下电 |
| 19 | SIM_OP20_IMEI_LOCK | OP20 IMEI 锁 |
| 20 | SIM_PLUG_IN_REPLACED | 插入了不同的 SIM 卡（换卡检测） |
| 21 | SIM_OP01_LOCK | OP01 锁定 |
| 22 | SIM_OP01_UNLOCK | OP01 解锁 |
| 23 | SIM_FAST_RECOVERY_START | 快速救卡开始（需 SBP_SIM_FAST_RECOVERY_REPORT 使能） |
| 24 | SIM_FAST_RECOVERY_SUCCESS | 快速救卡成功（需 SBP_SIM_FAST_RECOVERY_REPORT 使能） |
| 25 | SIM_TRAY_PLUG_OUT | SIM 卡托拔出 |
| 26 | SIM_PLUG_IN_NO_INIT | 插卡但不初始化 |
| 27 | SIM_PRESENCE_DETECTION_FAIL | SIM 存在检测失败 |
| 28 | SIM_STATE_DISABLE | SIM 状态禁用 |
| 29 | SIM_STATE_ENABLE | SIM 状态启用（SIM 通信就绪，但不代表识卡完成，需等 LOADED） |

## 关键判断规则

### 规则 1：不识卡检测
```
+ESIMS:1,29 后紧跟 +ESIMS:0,1 → 需要结合上下文判断
```

**重要：此序列有两种含义，必须区分：**

**情况 A：未插卡的 slot（正常打印）**
开机初始化时，未插卡的 slot 也会打印 `+ESIMS:1,29→0,1`，这是 Modem 尝试探测卡槽的正常行为，不代表硬件问题。

判断依据：
- 该 slot 后续无 `+ESIMS:0,13`（救卡）、无 `+ESIMS:0,11`（拔卡）
- 该 slot 始终 `CARDSTATE_ABSENT`
- 另一个 slot 正常识卡
- 用户截图只有一个 SIM 图标

**情况 B：已插卡的 slot（硬件接触问题）**
已插卡的 slot 出现 `+ESIMS:1,29→0,1`，说明 SIM 卡识别成功但无法正常访问。

判断依据：
- 该 slot 后续触发了救卡（`+ESIMS:0,13`）或拔出（`+ESIMS:0,11`）
- 有 `AnswerToReset` ATR 错误
- 用户反馈该 slot 不识卡
- 用户截图/Jira 确认该 slot 插了卡

**示例（情况 B）**：
```
10:55:22.664 handleSimStateChanged, +ESIMS:1,29
10:55:22.669 handleSimStateChanged, +ESIMS:0,1
10:55:22.670 handleSimStateChanged, +ESIMS:0,13  ← 触发救卡，确认是已插卡的slot
```

### 规则 2：正常识卡
```
+ESIMS:1,29 单独出现 → SIM 通信就绪，后续需确认达到 LOADED 才算真正识卡
```

**示例**：
```
10:55:22.664 handleSimStateChanged, +ESIMS:1,29
10:55:23.123 updateSimState: READY
10:55:23.456 updateSimState: LOADED  ← 到这里才算识卡完成
```
**判断**：正常识卡流程，以 LOADED 为准

### 规则 3：救卡成功
```
+ESIMS:0,13 和 +ESIMS:1,14 成对出现 → 救卡流程成功
```

**示例**：
```
10:54:59.452 handleSimStateChanged, +ESIMS:0,13
10:55:01.456 handleSimStateChanged, +ESIMS:1,14
10:55:01.789 handleSimStateChanged, +ESIMS:1,29
```
**判断**：接触不良触发救卡，救卡成功

### 规则 4：救卡失败
```
仅有 +ESIMS:0,13 无 +ESIMS:1,14 → 救卡失败
```

**示例**：
```
10:54:59.452 handleSimStateChanged, +ESIMS:0,13
[无后续 +ESIMS:1,14]
```
**判断**：救卡流程启动但未成功

## 典型序列模式

### 模式 1：正常热插拔
```
拔卡：+ESIMS:0,11
插卡：+ESIMS:1,12
识卡：+ESIMS:1,29
```

### 模式 2：热插拔后不识卡
```
拔卡：+ESIMS:0,11
插卡：+ESIMS:1,12
识卡：+ESIMS:1,29
错误：+ESIMS:0,1  ← 硬件接触问题
```

### 模式 3：救卡流程
```
救卡开始：+ESIMS:0,13
状态变化：updateSimState: ABSENT
救卡成功：+ESIMS:1,14
识卡完成：+ESIMS:1,29
状态恢复：updateSimState: READY → LOADED  ← LOADED 才算真正恢复
```

### 模式 4：快速插拔（异常）
```
拔卡：+ESIMS:0,11  (10:55:00.000)
插卡：+ESIMS:1,12  (10:55:00.500)  ← 间隔 < 1秒
拔卡：+ESIMS:0,11  (10:55:01.000)
插卡：+ESIMS:1,12  (10:55:01.500)
```
**判断**：快速插拔，可能导致识别异常

## 时间间隔分析

### 正常时间间隔
- 插卡到识卡：`+ESIMS:1,12` → `+ESIMS:1,29` 通常 < 2 秒
- 救卡流程：`+ESIMS:0,13` → `+ESIMS:1,14` 通常 1-3 秒

### 异常时间间隔
- 插卡到识卡 > 5 秒：可能存在识别延迟
- 救卡流程 > 10 秒：救卡过程异常缓慢
- 快速插拔 < 1 秒：可能导致识别失败

## 卡槽区分

AT+ESIMS 命令本身不包含卡槽信息，需要结合上下文判断：

**方法 1**：查看日志前缀
```
[SIM_DRV:0] → slot 0 (SIM1)
[SIM_DRV:1] → slot 1 (SIM2)
```

**方法 2**：查看 updateSimState
```
updateSimState: slot 0 READY → slot 0
updateSimState: slot 1 READY → slot 1
```

## 与其他日志的关联

### 与 ATR 的关联
```
+ESIMS:1,29 → 应该有对应的 ATR 日志
无 ATR 日志 + +ESIMS:0,1 → 硬件接触问题
```

### 与 updateSimState 的关联
```
+ESIMS:1,29 → updateSimState: READY（通信就绪，非最终识卡状态）
+ESIMS:0,1 → updateSimState: CARD_IO_ERROR
+ESIMS:0,13 → updateSimState: ABSENT
```

## 常见问题模式

### Q1：为什么 +ESIMS:1,29 后立即出现 +ESIMS:0,1？
**A**：硬件接触问题，SIM 卡识别成功但无法正常访问，通常是触点接触不良。

### Q2：救卡流程什么时候触发？
**A**：当检测到 SIM 卡接触不良或多次识别失败时，系统自动触发救卡机制。

### Q3：如何区分正常掉卡和硬件问题？
**A**：
- 正常掉卡：`LOADED → ABSENT`，可能是用户拔卡
- 硬件问题：`+ESIMS:1,29 → +ESIMS:0,1`，识别后立即错误

### Q4：eSIM 占用如何体现在 AT+ESIMS 中？
**A**：eSIM 占用时，物理 SIM 卡的热插拔事件会被忽略，不会产生 `+ESIMS:1,12` 等日志。

## 参考资料

- [SIM卡Skill开发 - AT+ESIMS命令详解](https://transsioner.feishu.cn/wiki/NEEBwlF1IiyVMWkXBP8cs7sEndb)
