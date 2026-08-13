# SIM 卡问题分析示例集

## 示例 1：硬件接触无 ATR 响应

### 问题描述
用户反馈："SIM 卡插入后不识卡，slot 0 无信号"

### Jira 信息
- 问题类型：SIM 卡不识卡
- 影响卡槽：slot 0 (SIM1)
- 问题时间：2026-01-12 10:55:22

### 分析流程

#### 步骤 1：确认基本信息
- 插入卡数：双卡
- 问题卡槽：slot 0
- 时间窗：10:55:00 - 10:56:00

#### 步骤 2：硬件问题排查
搜索 `AnswerToReset`：
```
10:55:22.789 AnswerToReset: Valid ATR string must at least contains TS and T0.
```
**发现**：有 ATR 错误

搜索 `No ATR`：
```
10:55:22.800 [SIM_DRV:0][ERR]No ATR
```
**确认**：slot 0 无 ATR 响应

#### 步骤 3：AT+ESIMS 序列分析
```
10:55:21.778 handleSimStateChanged, +ESIMS:1,12 (插卡)
10:55:22.664 handleSimStateChanged, +ESIMS:1,29 (识卡)
10:55:22.669 handleSimStateChanged, +ESIMS:0,1 (错误)
```
**发现**：+ESIMS:1,29 后紧跟 +ESIMS:0,1

#### 步骤 4：状态流转分析
```
10:55:00.000 updateSimState: slot 0 ABSENT
10:55:22.789 updateSimState: slot 0 CARD_IO_ERROR
```
**发现**：状态直接从 ABSENT 到 CARD_IO_ERROR

#### 步骤 5：特殊场景检测
- 无 PIN 锁
- 无 eSIM 占用
- 无 Modem 异常

### 关键证据
```
[证据1] AnswerToReset: Valid ATR string must at least contains TS and T0.
[证据2] [SIM_DRV:0][ERR]No ATR
[证据3] +ESIMS:1,29 后紧跟 +ESIMS:0,1
[证据4] updateSimState: slot 0 CARD_IO_ERROR
```

### 输出结果
```json
{
  "problem_classification": "HARDWARE_NO_ATR",
  "affected_slot": 0,
  "root_cause": "SIM 卡触点接触不良，无法读取 ATR",
  "timeline": [
    {
      "time": "10:55:21.778",
      "slot": 0,
      "event": "插卡",
      "code": "+ESIMS:1,12",
      "description": "用户插入 SIM 卡"
    },
    {
      "time": "10:55:22.664",
      "slot": 0,
      "event": "识卡",
      "code": "+ESIMS:1,29",
      "description": "SIM 卡识别成功"
    },
    {
      "time": "10:55:22.669",
      "slot": 0,
      "event": "错误",
      "code": "+ESIMS:0,1",
      "description": "访问错误，不识卡"
    }
  ],
  "evidence": [
    "AnswerToReset: Valid ATR string must at least contains TS and T0.",
    "[SIM_DRV:0][ERR]No ATR",
    "+ESIMS:1,29 后紧跟 +ESIMS:0,1",
    "updateSimState: slot 0 CARD_IO_ERROR"
  ],
  "recommendation": "清洁 SIM 卡触点，重新插入测试；如问题持续，更换卡槽测试"
}
```

---

## 示例 2：救卡流程成功

### 问题描述
用户反馈："SIM 卡出现短暂无信号，然后自动恢复"

### Jira 信息
- 问题类型：SIM 卡掉卡
- 影响卡槽：slot 0 (SIM1)
- 问题时间：2026-01-12 10:54:59

### 分析流程

#### 步骤 1：确认基本信息
- 插入卡数：单卡
- 问题卡槽：slot 0
- 时间窗：10:54:50 - 10:55:10

#### 步骤 2：硬件问题排查
搜索 `AnswerToReset`：无错误
搜索 `No ATR`：无错误
**结论**：无硬件问题

#### 步骤 3：AT+ESIMS 序列分析
```
10:54:59.452 handleSimStateChanged, +ESIMS:0,13 (救卡开始)
10:55:01.456 handleSimStateChanged, +ESIMS:1,14 (救卡成功)
10:55:01.789 handleSimStateChanged, +ESIMS:1,29 (识卡成功)
```
**发现**：有完整的救卡流程

#### 步骤 4：状态流转分析
```
10:54:59.000 updateSimState: slot 0 LOADED (正常使用中)
10:54:59.500 updateSimState: slot 0 ABSENT (掉卡)
10:55:02.012 updateSimState: slot 0 READY (恢复)
10:55:02.345 updateSimState: slot 0 LOADED (完全恢复)
```
**发现**：状态从 LOADED → ABSENT → READY → LOADED

#### 步骤 5：特殊场景检测
- 无 PIN 锁
- 无 eSIM 占用
- 无 Modem 异常

### 时间线
```
10:54:59.000 [0] 正常使用 LOADED 状态
10:54:59.452 [0] 救卡开始 +ESIMS:0,13 接触不良检测
10:54:59.500 [0] 掉卡 ABSENT 状态
10:55:01.456 [0] 救卡成功 +ESIMS:1,14 救卡机制生效
10:55:01.789 [0] 识卡成功 +ESIMS:1,29 重新识别
10:55:02.012 [0] 就绪 READY 状态
10:55:02.345 [0] 恢复 LOADED 状态
```

### 输出结果
```json
{
  "problem_classification": "RECOVERY_SUCCESS",
  "affected_slot": 0,
  "root_cause": "接触不良导致短暂掉卡，救卡机制自动恢复",
  "recovery_duration": "2.9秒",
  "recommendation": "虽然已恢复，但建议检查 SIM 卡和卡槽状态，避免再次发生"
}
```

---

## 示例 3：eSIM 占用物理卡槽

### 问题描述
用户反馈："SIM2 插入后无反应，热插拔无效"

### Jira 信息
- 问题类型：SIM 卡不识卡
- 影响卡槽：slot 1 (SIM2)
- 问题时间：2026-01-12 11:00:00

### 分析流程

#### 步骤 1：确认基本信息
- 插入卡数：双卡
- 问题卡槽：slot 1
- 时间窗：11:00:00 - 11:01:00

#### 步骤 2：硬件问题排查
搜索 `AnswerToReset`：无错误
搜索 `No ATR`：无错误
**结论**：无硬件问题

#### 步骤 3：AT+ESIMS 序列分析
```
[无 slot 1 的 +ESIMS 日志]
```
**发现**：slot 1 完全没有 AT+ESIMS 事件

#### 步骤 4：状态流转分析
```
11:00:00.000 updateSimState: slot 1 ABSENT
[无后续状态变化]
```
**发现**：slot 1 一直保持 ABSENT 状态

#### 步骤 5：特殊场景检测
搜索 `eSIM ignore`：
```
11:00:05.123 [SIM_CUS_DRV:1]: eSIM ignore hot plug.
11:00:05.456 MSG_ID_SIM_ERROR_IND
```
**发现**：eSIM 占用 slot 1

### 关键证据
```
[证据1] [SIM_CUS_DRV:1]: eSIM ignore hot plug.
[证据2] MSG_ID_SIM_ERROR_IND
[证据3] slot 1 无任何 +ESIMS 事件
[证据4] slot 1 一直保持 ABSENT 状态
```

### 输出结果
```json
{
  "problem_classification": "ESIM_CONFLICT",
  "affected_slot": 1,
  "root_cause": "eSIM 已激活，物理 SIM2 卡槽被占用",
  "recommendation": "检查 eSIM 配置，如需使用物理卡请禁用 eSIM"
}
```

---

## 示例 4：PIN 锁状态

### 问题描述
用户反馈："SIM 卡插入后显示 PIN_REQUIRED"

### Jira 信息
- 问题类型：SIM 卡 PIN 锁
- 影响卡槽：slot 0 (SIM1)
- 问题时间：2026-01-12 12:00:00

### 分析流程

#### 步骤 1：确认基本信息
- 插入卡数：单卡
- 问题卡槽：slot 0
- 时间窗：12:00:00 - 12:01:00

#### 步骤 2：硬件问题排查
搜索 `AnswerToReset`：无错误
搜索 `No ATR`：无错误
**结论**：无硬件问题

#### 步骤 3：AT+ESIMS 序列分析
```
12:00:21.778 handleSimStateChanged, +ESIMS:1,12 (插卡)
12:00:22.664 handleSimStateChanged, +ESIMS:1,29 (识卡成功)
```
**发现**：识卡成功，无访问错误

#### 步骤 4：状态流转分析
```
12:00:00.000 updateSimState: slot 0 ABSENT
12:00:22.789 updateSimState: slot 0 PIN_REQUIRED
[无后续 READY 状态]
```
**发现**：停留在 PIN_REQUIRED 状态

#### 步骤 5：特殊场景检测
- 有 PIN 锁 ✅
- 无 eSIM 占用
- 无 Modem 异常

### 时间线
```
12:00:00.000 [0] 未插卡 ABSENT 状态
12:00:21.778 [0] 插卡 +ESIMS:1,12 用户插入 SIM 卡
12:00:22.664 [0] 识卡 +ESIMS:1,29 SIM 卡识别成功
12:00:22.789 [0] PIN锁 PIN_REQUIRED 等待输入 PIN 码
```

### 输出结果
```json
{
  "problem_classification": "PIN_LOCK",
  "affected_slot": 0,
  "root_cause": "SIM 卡 PIN 锁已开启",
  "recommendation": "提示用户输入正确的 PIN 码解锁"
}
```

---

## 示例 5：多次热插拔导致识别异常

### 问题描述
用户反馈："多次插拔 SIM 卡后，只显示运营商不显示号码"

### Jira 信息
- 问题类型：SIM 卡识别异常
- 影响卡槽：slot 0 (SIM1)
- 问题时间：2026-01-12 13:00:00

### 分析流程

#### 步骤 1：确认基本信息
- 插入卡数：单卡
- 问题卡槽：slot 0
- 时间窗：13:00:00 - 13:01:00

#### 步骤 2：硬件问题排查
搜索 `AnswerToReset`：无错误
搜索 `No ATR`：无错误
**结论**：无硬件问题

#### 步骤 3：AT+ESIMS 序列分析
```
13:00:00.000 +ESIMS:0,11 (拔卡)
13:00:00.500 +ESIMS:1,12 (插卡)  ← 间隔 0.5秒
13:00:01.000 +ESIMS:0,11 (拔卡)
13:00:01.500 +ESIMS:1,12 (插卡)
13:00:02.000 +ESIMS:0,11 (拔卡)
13:00:02.500 +ESIMS:1,12 (插卡)
13:00:03.000 +ESIMS:0,11 (拔卡)
13:00:03.500 +ESIMS:1,12 (插卡)
13:00:04.000 +ESIMS:1,29 (识卡)
```
**发现**：4 次快速插拔（间隔 < 1 秒）

#### 步骤 4：状态流转分析
```
13:00:04.123 updateSimState: slot 0 READY
[长时间停留在 READY，未进入 LOADED]
```
**发现**：停留在 READY 状态，未完全加载

#### 步骤 5：特殊场景检测
- 无 PIN 锁
- 无 eSIM 占用
- 无 Modem 异常

### 热插拔统计
- 插拔次数：4 次
- 时间跨度：3.5 秒
- 平均间隔：0.875 秒
- 判断：快速插拔异常

### 输出结果
```json
{
  "problem_classification": "HOT_PLUG_ISSUE",
  "affected_slot": 0,
  "root_cause": "多次快速插拔导致 SIM 卡数据加载异常",
  "hot_plug_count": 4,
  "recommendation": "重启设备或重新插入 SIM 卡（插入后等待 5 秒再操作）"
}
```

---

## 分析模板

### 基本信息模板
```
- 问题类型：[不识卡/掉卡/PIN锁/...]
- 影响卡槽：[slot 0/slot 1]
- 问题时间：[YYYY-MM-DD HH:MM:SS]
- 时间窗：[开始时间 - 结束时间]
```

### 证据收集模板
```
[证据1] [日志类型] [关键日志内容]
[证据2] [日志类型] [关键日志内容]
[证据3] [日志类型] [关键日志内容]
```

### 输出结果模板
```json
{
  "problem_classification": "[问题分类]",
  "affected_slot": [0/1],
  "root_cause": "[根因描述]",
  "timeline": [...],
  "evidence": [...],
  "recommendation": "[处理建议]"
}
```

## 参考资料

- [SIM卡Skill开发 - 分析示例](https://transsioner.feishu.cn/wiki/NEEBwlF1IiyVMWkXBP8cs7sEndb)
