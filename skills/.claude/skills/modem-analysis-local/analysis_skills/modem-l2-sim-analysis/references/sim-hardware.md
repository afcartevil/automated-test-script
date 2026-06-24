# SIM 卡硬件问题检测

## 检测优先级
硬件问题是 SIM 分析的最高优先级，必须首先排查。

## ATR 响应检测

### AP 层（radio_log / main_log）
- 错误：`AnswerToReset: Valid ATR string must at least contains TS and T0.`
- 正常：有完整 ATR 字符串

### Modem 层（ps.txt）
- 错误：`[SIM_DRV:0][ERR]No ATR` / `[SIM_DRV:1][ERR]No ATR`
- 正常：`[SIM]ATR: 3B 9F 96 ...`
- 引脚状态：`[ESIM_PINS] : 0, 0, 0`（全 0 = 物理断开）
- 复位错误：`SIM_RESET_ERROR: DCL_USIM_NO_ATR`
- 检测结果：`SIM_DETECT_NO_ATR_ERR`

## 硬件问题分类

| 类型 | 特征 | 根因 |
|------|------|------|
| 完全无响应 | 无 ATR + 无 `+ESIMS:1,29` + 保持 ABSENT | 未插入/卡槽故障/卡损坏 |
| 接触不良 | `+ESIMS:1,29→0,1` + 后续有救卡(`0,13`)/拔出(`0,11`) + ATR 错误 | 触点氧化/弹片松动/卡变形 |
| 间歇性故障 | 时而有 ATR 时而无 + 触发救卡 | 接触不稳定/弹片疲劳 |

## 决策树

```
有 ATR 错误？
├─ 是 → 该 slot 有后续救卡(0,13)或拔出(0,11)？
│       ├─ 是 → 接触不良（已插卡，识别成功但无法访问）
│       └─ 否 → 检查是否未插卡（开机时 1,29→0,1 是未插卡的正常打印）
└─ 否 → +ESIMS:1,29→0,1？
        ├─ 有后续救卡/拔出 → 接触不良
        ├─ 无后续事件 + 始终 ABSENT → 可能未插卡（正常）
        └─ 检查热插拔模式
```

## eSIM 占用检测（仅 slot 1）
- Modem 日志：`[SIM_CUS_DRV:1]: eSIM ignore hot plug.`
- 错误指示：`MSG_ID_SIM_ERROR_IND`
- 特征：slot 1 完全无 +ESIMS 事件

## eSIM 开关状态检测

### 关键日志（radio_log）

**eSIM 开关打开（切换到 eSIM 模式）：**
```
SEND MSGID=057f [MIPC_SIM_ESIM_SWITCH_SET_REQ] ... MODE=01（1=switch to esim）
RECV MSGID=0580 [MIPC_SIM_ESIM_SWITCH_SET_CNF] ... ESIM_PSIM_STATE=01（1=esim）
```

**eSIM 开关关闭（切换到 pSIM 模式）：**
```
SEND MSGID=057f [MIPC_SIM_ESIM_SWITCH_SET_REQ] ... MODE=00（0=switch to psim）
RECV MSGID=0580 [MIPC_SIM_ESIM_SWITCH_SET_CNF] ... ESIM_PSIM_STATE=00（0=psim）
```

**eSIM 卡槽标识（Slot 1 有 EID）：**
```
handleGetSimStatusResponse: [1] ... eid:32,890340  ← eid 非 0 说明是 eSIM 卡槽
```

### DUMP 字段解析（MIPC_SIM_ESIM_SWITCH_SET_REQ）
- `MODE`（T=0x100）：`01` = 切换到 eSIM，`00` = 切换到 pSIM

### DUMP 字段解析（MIPC_SIM_ESIM_SWITCH_SET_CNF）
- `ESIM_SUPPORT`（T=0x100）：是否支持 eSIM
- `ESIM_PSIM_STATE`（T=0x101）：`00` = 当前 pSIM 模式，`01` = 当前 eSIM 模式

### 重要规则

**规则：eSIM 开关已打开时，热插拔不会触发 +ESIMS 事件**

当 eSIM 开关处于打开状态（ESIM_PSIM_STATE=1）时，Slot 1 的物理 SIM 卡热插拔动作不会产生 `+ESIMS:0,11`（SIM_PLUG_OUT）或 `+ESIMS:1,12`（SIM_PLUG_IN）打印。这是正常行为，不代表硬件故障。

判断流程：
```
Slot 1 无热插拔 +ESIMS 事件？
├─ 检查是否有 MIPC_SIM_ESIM_SWITCH_SET_REQ（MODE=01）
│   ├─ 有 → eSIM 开关已打开，热插拔被屏蔽，属正常行为
│   └─ 无 → 检查 eid 字段是否非 0
│           ├─ eid 非 0 → 该 slot 为 eSIM 卡槽，eSIM 可能已预先激活
│           └─ eid = 0 → 排查其他原因（eSIM ignore hot plug / 硬件问题）
```

### 实际案例（LK6 不识卡）
```
13:09:05.374  MIPC_SIM_ESIM_SWITCH_SET_REQ MODE=01 → eSIM 开关打开
13:09:05.491  MIPC_SIM_ESIM_SWITCH_SET_CNF ESIM_PSIM_STATE=01 → 确认切换到 eSIM
13:09:05.551  [Slot 1] +ESIMS:0,11 → 切换触发的拔卡事件
13:09:06.841  [Slot 1] +ESIMS:1,29 → eid:32,890340 → Slot 1 是 eSIM 卡槽
13:09:06.849  [Slot 1] +ESIMS:0,1  → eSIM 无 profile，访问失败（正常）
```
结论：Slot 1 的异常是 eSIM 切换导致，非硬件问题。Slot 0 的 ATR 错误才是真正的接触不良。
