# L3 结论与建议 Playbook

AI 必须按照本文档逐步生成最终结论。

## Step 1: 汇总 L0/L1/L2 结果

读取以下分析结果：
- `manifest.analysis.l0_baseline`: L0 基础指标
- `manifest.analysis.l1_business`: L1 业务判断
- `manifest.analysis.l2_domains.*`: L2 域内分析

## Step 2: 提取主要根因

从 L2 结果中提取 `candidate_root_causes`，选择 confidence 最高的作为主要根因。

**根因类型判定**：
| L1 primary_domain | 根因来源 |
|-------------------|---------|
| `sim` | L2-sim 的 candidate_root_causes |
| `call` | L2-call 的 candidate_root_causes |
| `data` | L2-data 的 candidate_root_causes |
| `other` | L0 异常指标 |

## Step 3: 提取次要因素

从 L0/L2 结果中提取可能影响问题的次要因素：

| 来源 | 次要因素示例 |
|------|-------------|
| L0 信号指标 | 信号质量差、调度效率低 |
| L0 弱网状态 | RAT 频繁切换 |
| L2 时间线 | 问题发生前的异常事件 |

## Step 4: 生成建议

根据根因生成具体的下一步建议：

| 根因类型 | 建议动作 |
|---------|---------|
| 网络侧问题 | 提取网络侧日志、联系运营商 |
| 终端配置问题 | 检查 APN 配置、检查 IMS 配置 |
| SIM 卡问题 | 更换 SIM 卡测试、检查卡槽 |
| 硬件问题 | 检查设备硬件、更换设备测试 |
| 信号问题 | 更换测试地点、检查天线 |

## Step 5: 记录缺口

明确列出分析中缺失的信息。

## Step 6: 生成最终报告

按照以下模板生成 `final_report` 文本：

```
## 分析结论

- **问题类型**: [call/data/sim/other]
- **主要根因**: [根因描述]
- **置信度**: [high/medium/low]

## 问题时间线

| 时间 | 事件 | 详情 |
|------|------|------|
| [时间戳] | [事件描述] | [详细信息] |

## 关键证据

1. [时间戳] [证据描述]
2. [时间戳] [证据描述]

## 根因分析

### 主要根因：[根因名称]

**判定依据**：
- [依据1]
- [依据2]

### 次要因素：
- [次要因素1]
- [次要因素2]

## 建议下一步

1. [建议1]
2. [建议2]

## 缺失信息

- [缺失信息1]
```

## 输出格式

将结果写入 `manifest.analysis.l3_conclusion` 和 `manifest.analysis.final_report`：

```json
{
  "analysis": {
    "l3_conclusion": {
      "conclusion_type": "valid",
      "issue_type": "call|data|sim|other",
      "primary_root_cause": {
        "cause": "...",
        "confidence": "high|medium|low",
        "evidence": ["...", "..."]
      },
      "secondary_factors": [
        {"factor": "...", "impact": "..."}
      ],
      "recommendations": ["建议1", "建议2"],
      "gaps": ["...", "..."],
      "status": "completed"
    },
    "final_report": "## 分析结论\n\n**问题类型**: ...\n..."
  }
}
```

## 分析示例

### 示例: SIM 卡不识别

**L0 结果**：SIM 状态 abnormal (no_atr)
**L1 结果**：primary_domain = "sim"
**L2 结果**：
```json
{
  "sim_type": "physical",
  "problem_type": "not_detected",
  "slot_info": {
    "slot_0": {"status": "error", "error_type": "no_atr"},
    "slot_1": {"status": "error", "error_type": "no_atr"}
  },
  "candidate_root_causes": [
    {
      "cause": "设备读卡器硬件故障",
      "confidence": "high",
      "evidence": ["两个卡槽都报 No ATR", "物理复位失败"]
    }
  ]
}
```

**生成的 final_report**：
```
## 分析结论

**问题类型**: SIM 卡不识别
**主要根因**: 设备读卡器硬件故障，导致两个 SIM 卡槽都无法获取 ATR 响应
**置信度**: high

## 问题时间线

| 时间 | 事件 | 详情 |
|------|------|------|
| 16:53:51.805 | 开始物理卡复位 | [MEP][physical_card_reset] reset_start(1) |
| 16:53:51.805 | SIM 卡槽 0 无响应 | [SIM_DRV:0][ERR]No ATR |
| 16:53:51.805 | SIM 卡槽 1 无响应 | [SIM_DRV:1][ERR]No ATR |
| 16:53:52.435 | 物理复位失败 | error_cause: DCL_USIM_NO_ATR |

## 关键证据

1. 16:53:51 [SIM_DRV:0][ERR]No ATR - SIM 卡槽 0 无响应
2. 16:53:51 [SIM_DRV:1][ERR]No ATR - SIM 卡槽 1 无响应
3. 16:53:52 [MEP][physical_card_reset] error_cause: DCL_USIM_NO_ATR - 物理复位失败

## 根因分析

### 主要根因：设备读卡器硬件故障

**判定依据**：
- 两个 SIM 卡槽同时报 No ATR 错误
- 如果是单张 SIM 卡损坏，通常只会影响一个卡槽
- 两个卡槽都无法获取 ATR，更可能是设备读卡器硬件问题

### 次要因素：
- 信号指标加权平均分 5.35（低于阈值 6）

## 建议下一步

1. 检查设备读卡器硬件状态，确认是否存在硬件故障
2. 更换 SIM 卡测试，排除 SIM 卡损坏的可能性
3. 如换卡后仍报 No ATR，建议更换设备进行对比测试

## 缺失信息

- 换卡测试结果
- 设备读卡器硬件检测结果
```
