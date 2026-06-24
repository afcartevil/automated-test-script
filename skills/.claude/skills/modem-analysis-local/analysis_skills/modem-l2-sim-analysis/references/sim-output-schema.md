# L2 SIM 分析输出结构定义

## 输出位置

```
analysis.l2_domains.sim
```

## 完整结构

```json
{
  "analysis_type": "sim",
  "problem_classification": "string",
  "affected_slot": 0 | 1 | null,
  "root_cause": "string",
  "timeline": [
    {
      "timestamp": "string",
      "slot": 0 | 1,
      "event_type": "string",
      "event_code": "string",
      "description": "string",
      "log_source": "string"
    }
  ],
  "evidence": [
    {
      "type": "string",
      "content": "string",
      "log_file": "string",
      "timestamp": "string",
      "relevance": "high" | "medium" | "low"
    }
  ],
  "candidate_causes": [
    {
      "cause": "string",
      "confidence": "high" | "medium" | "low",
      "supporting_evidence": ["string"]
    }
  ],
  "state_flow": {
    "slot_0": [
      {
        "timestamp": "string",
        "state": "string",
        "duration": "string"
      }
    ],
    "slot_1": [
      {
        "timestamp": "string",
        "state": "string",
        "duration": "string"
      }
    ]
  },
  "at_esims_sequence": [
    {
      "timestamp": "string",
      "slot": 0 | 1,
      "inserted_status": 0 | 1,
      "cause": "number",
      "interpretation": "string"
    }
  ],
  "hardware_detection": {
    "atr_response": {
      "slot_0": "success" | "failed" | "unknown",
      "slot_1": "success" | "failed" | "unknown"
    },
    "hot_plug_analysis": {
      "count": "number",
      "time_span": "string",
      "abnormal_patterns": ["string"]
    }
  },
  "special_scenarios": {
    "pin_lock": {
      "detected": "boolean",
      "slot": 0 | 1 | null
    },
    "esim_conflict": {
      "detected": "boolean",
      "slot": 1 | null
    },
    "modem_crash": {
      "detected": "boolean",
      "crash_type": "string"
    },
    "recovery_process": {
      "triggered": "boolean",
      "success": "boolean",
      "duration": "string"
    }
  },
  "gaps": ["string"],
  "recommendations": ["string"]
}
```

## 字段说明

### problem_classification
问题分类，可选值：
- `HARDWARE_NO_ATR` - 硬件接触无 ATR 响应
- `SIM_ACCESS_ERROR` - SIM 卡访问错误
- `HOT_PLUG_ISSUE` - 热插拔异常
- `PIN_LOCK` - PIN 锁状态
- `RECOVERY_SUCCESS` - 救卡成功
- `RECOVERY_FAILED` - 救卡失败
- `ESIM_CONFLICT` - eSIM 占用
- `MODEM_CRASH` - Modem 异常
- `NORMAL` - 正常识卡

### affected_slot
受影响的卡槽：
- `0` - slot 0 (SIM1)
- `1` - slot 1 (SIM2)
- `null` - 未确定或双卡都受影响

### root_cause
根因描述，简洁明了的一句话说明

### timeline
时间线数组，按时间顺序记录关键事件

#### event_type
事件类型：
- `plug_out` - 拔卡
- `plug_in` - 插卡
- `sim_detected` - 识卡
- `sim_error` - 错误
- `recovery_start` - 救卡开始
- `recovery_end` - 救卡成功
- `state_change` - 状态变化

### evidence
证据数组，支持根因判断的关键日志

#### type
证据类型：
- `atr_error` - ATR 错误
- `at_esims` - AT+ESIMS 命令
- `state_change` - 状态变化
- `modem_log` - Modem 日志
- `system_error` - 系统错误

#### relevance
相关性：
- `high` - 高相关性，直接支持根因
- `medium` - 中等相关性，辅助证据
- `low` - 低相关性，背景信息

### candidate_causes
候选根因数组，可能的多个根因

#### confidence
置信度：
- `high` - 高置信度（> 80%）
- `medium` - 中等置信度（50-80%）
- `low` - 低置信度（< 50%）

### state_flow
状态流转记录，分别记录两个卡槽的状态变化

#### state
状态值：
- `ABSENT` - 卡不存在
- `UNKNOWN` - 未知状态
- `READY` - 就绪
- `LOADED` - 已加载
- `PIN_REQUIRED` - 需要 PIN
- `PUK_REQUIRED` - 需要 PUK
- `CARD_IO_ERROR` - 卡 IO 错误
- `CARD_RESTRICTED` - 卡受限

### at_esims_sequence
AT+ESIMS 命令序列，完整记录所有 ESIMS 事件

#### inserted_status
- `0` - SIM 卡未插入
- `1` - SIM 卡已插入

#### cause
状态码，参见 `at-esims-reference.md`

### hardware_detection
硬件检测结果

#### atr_response
ATR 响应状态：
- `success` - 成功
- `failed` - 失败
- `unknown` - 未知

### special_scenarios
特殊场景检测结果

### gaps
分析缺口，未能确认的项目

### recommendations
处理建议，具体的排查和处理步骤

## 输出示例

### 示例 1：硬件接触问题
```json
{
  "analysis_type": "sim",
  "problem_classification": "HARDWARE_NO_ATR",
  "affected_slot": 0,
  "root_cause": "SIM 卡触点接触不良，无法读取 ATR",
  "timeline": [
    {
      "timestamp": "2026-01-12T10:55:21.778",
      "slot": 0,
      "event_type": "plug_in",
      "event_code": "+ESIMS:1,12",
      "description": "用户插入 SIM 卡",
      "log_source": "radio_log"
    },
    {
      "timestamp": "2026-01-12T10:55:22.664",
      "slot": 0,
      "event_type": "sim_detected",
      "event_code": "+ESIMS:1,29",
      "description": "SIM 卡识别成功",
      "log_source": "radio_log"
    },
    {
      "timestamp": "2026-01-12T10:55:22.669",
      "slot": 0,
      "event_type": "sim_error",
      "event_code": "+ESIMS:0,1",
      "description": "访问错误，不识卡",
      "log_source": "radio_log"
    }
  ],
  "evidence": [
    {
      "type": "atr_error",
      "content": "AnswerToReset: Valid ATR string must at least contains TS and T0.",
      "log_file": "main_log",
      "timestamp": "2026-01-12T10:55:22.789",
      "relevance": "high"
    },
    {
      "type": "modem_log",
      "content": "[SIM_DRV:0][ERR]No ATR",
      "log_file": "modem_log",
      "timestamp": "2026-01-12T10:55:22.800",
      "relevance": "high"
    },
    {
      "type": "state_change",
      "content": "updateSimState: slot 0 CARD_IO_ERROR",
      "log_file": "main_log",
      "timestamp": "2026-01-12T10:55:22.789",
      "relevance": "high"
    }
  ],
  "candidate_causes": [
    {
      "cause": "SIM 卡触点接触不良",
      "confidence": "high",
      "supporting_evidence": [
        "ATR 错误",
        "+ESIMS:1,29 后紧跟 +ESIMS:0,1",
        "CARD_IO_ERROR 状态"
      ]
    }
  ],
  "state_flow": {
    "slot_0": [
      {
        "timestamp": "2026-01-12T10:55:00.000",
        "state": "ABSENT",
        "duration": "22.789s"
      },
      {
        "timestamp": "2026-01-12T10:55:22.789",
        "state": "CARD_IO_ERROR",
        "duration": "ongoing"
      }
    ],
    "slot_1": []
  },
  "at_esims_sequence": [
    {
      "timestamp": "2026-01-12T10:55:21.778",
      "slot": 0,
      "inserted_status": 1,
      "cause": 12,
      "interpretation": "插卡"
    },
    {
      "timestamp": "2026-01-12T10:55:22.664",
      "slot": 0,
      "inserted_status": 1,
      "cause": 29,
      "interpretation": "识卡成功"
    },
    {
      "timestamp": "2026-01-12T10:55:22.669",
      "slot": 0,
      "inserted_status": 0,
      "cause": 1,
      "interpretation": "访问错误"
    }
  ],
  "hardware_detection": {
    "atr_response": {
      "slot_0": "failed",
      "slot_1": "unknown"
    },
    "hot_plug_analysis": {
      "count": 1,
      "time_span": "0s",
      "abnormal_patterns": []
    }
  },
  "special_scenarios": {
    "pin_lock": {
      "detected": false,
      "slot": null
    },
    "esim_conflict": {
      "detected": false,
      "slot": null
    },
    "modem_crash": {
      "detected": false,
      "crash_type": null
    },
    "recovery_process": {
      "triggered": false,
      "success": false,
      "duration": null
    }
  },
  "gaps": [],
  "recommendations": [
    "清洁 SIM 卡触点，重新插入测试",
    "如问题持续，更换卡槽测试",
    "检查 SIM 卡是否变形或损坏"
  ]
}
```

### 示例 2：救卡成功
```json
{
  "analysis_type": "sim",
  "problem_classification": "RECOVERY_SUCCESS",
  "affected_slot": 0,
  "root_cause": "接触不良导致短暂掉卡，救卡机制自动恢复",
  "special_scenarios": {
    "recovery_process": {
      "triggered": true,
      "success": true,
      "duration": "2.9s"
    }
  },
  "recommendations": [
    "虽然已恢复，但建议检查 SIM 卡和卡槽状态",
    "避免再次发生接触不良"
  ]
}
```

## 注意事项

1. 所有时间戳使用 ISO 8601 格式
2. 证据必须包含完整的日志内容和来源
3. 根因必须有充分的证据支持
4. 缺口（gaps）必须明确说明
5. 建议（recommendations）必须具体可操作

## 参考资料

- [通信skill框架 - 输出结构规范](https://transsioner.feishu.cn/wiki/FySdwXwoBiqBchkKnvKcIoCGnAN)
