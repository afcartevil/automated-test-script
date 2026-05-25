---
name: mtk-tp-touch-log-analysis
description: "MTK-TP触摸: 分析TP触摸失效问题，检查kernel_log中TP驱动初始化、IC匹配、触摸上报、失败签名 | tpd_probe/match_tp_controller/fts_input_report/TP无触摸/开机触摸失效/亮灭屏无触摸/误触 | 当用户报告MTK设备触摸失效、开机无触摸、亮灭屏后触摸丢失、TP误触时使用。手势唤醒问题走mtk-tp-gesture-log-analysis，屏下指纹走mtk-tp-fod-log-analysis"
---

# MTK TP 触摸异常日志分析

## 适用范围

- **问题类型**：TP 触摸失效 / TP 驱动加载失败相关问题
- **适用场景**：
  - 手机开机 TP 失效
  - 亮灭屏后无触摸
  - 触摸误触，需要先确认 TP 是否已正常上报
- **适用芯片平台**：MTK

## 前置条件

分析前需确认以下日志文件可用：

| 日志文件 | 必需性 | 用途 |
|---|---|---|
| `kernel_log` | 必需 | 分析内核阶段 TP 初始化、IC 识别、驱动加载和触摸上报情况 |
| `mobilelog` | 建议 | 从 JIRA 或日志目录中提取可分析日志 |
| `boot_normal/kernel_log` | 建议 | 优先查看开机阶段 TP 驱动加载链路 |

## 问题有效性确认

开始分析前，先确认：

- 手机屏幕无明显损坏

## 分析工作流

按以下顺序执行，详细操作参阅 [ANALYSIS_STEPS.md](ANALYSIS_STEPS.md)。

### 步骤1：获取日志
- **目标**：拿到与 TP 触摸失效直接相关的日志
- **操作**：
  - 从 JIRA 的 `Log and Screenshot address` 获取 `mobilelog` 或用户提供的 log 地址
  - 获取 `mobilelog` 后，提取 APLog 中的 `kernel_log` 和 `boot_normal` 中的 `kernel_log`
- **判断**：
  - 未获取到 `kernel_log` -> 停止分析并说明缺失日志
  - 已获取到 `kernel_log` -> 进入步骤2

### 步骤2：判断问题
- **目标**：先按问题类型收敛到对应时间段
- **操作**：
  - 开机无触摸：查看 `boot_normal` 中的 `kernel_log`
  - 亮灭屏无触摸：查看对应时间点的 `kernel_log`
- **判断**：
  - 已定位到对应问题时间段 -> 进入步骤3

### 步骤3：分析日志
- **目标**：确认 TP 驱动是否正常初始化、是否有失败报错，以及触摸数据是否成功上报
- **重点检查**：
  - 是否存在初始化成功关键字
  - 若未成功，具体失败报错是什么
  - 若初始化成功，是否存在触摸数据上报
  - 若已有触摸数据上报，是否应转交上层继续分析

## 关键字速查

- 关键词与原始日志示例：参阅 [KEYWORDS.md](KEYWORDS.md)
- 常见问题与根因对照：参阅 [COMMON_ISSUES.md](COMMON_ISSUES.md)
- 典型案例：参阅 [CASES.md](CASES.md)

核心搜索关键字：

```text
kernel_log: tran_touch|fts|nvt|omn|ilitek|tpd_probe|match_tp_controller|fts_input_report_b
```

## 输出格式

按以下模板输出分析结论：

```markdown
# MTK TP 触摸异常日志分析报告

## 基本信息
- 分析时间：[时间]
- 日志来源：[文件列表]
- 问题描述：[用户提供的问题描述]
- 芯片平台：[平台信息，如可确定]

## 分析过程
### 步骤1：获取日志
- 搜索/检查目标：[JIRA / 目录 / 日志文件来源]
- 搜索结果：[是否拿到 mobilelog、kernel_log、boot_normal/kernel_log]
- 判断结论：[是否满足继续分析条件]

### 步骤2：判断问题
- 问题类型：[开机无触摸 / 亮灭屏无触摸 / 误触]
- 目标时间段：[对应日志范围]
- 判断结论：[后续重点查看的 kernel_log 位置]

### 步骤3：分析日志
- 初始化成功关键字：[有/无，关键日志]
- 初始化失败报错：[有/无，关键日志]
- 触摸数据上报：[有/无，关键日志]
- 判断结论：[TP 侧结论或是否转交上层]

## 分析结论
- 问题根因：[根因描述]
- 证据摘要：[支持结论的关键日志行]
- 置信度：[高/中/低]
- 建议措施：[后续处理建议]
```

## 参考信息

- 关键字与日志示例：参阅 [KEYWORDS.md](KEYWORDS.md)
- 常见问题对照：参阅 [COMMON_ISSUES.md](COMMON_ISSUES.md)
- 典型案例参考：参阅 [CASES.md](CASES.md)

## 约束

- 不要假装看过未提供的日志。
- 没有 `kernel_log` 时，不要直接对 TP 侧下结论。
- 如果已经看到 TP 初始化成功且有触摸数据上报，不要继续把问题直接定性为 TP 驱动加载失败。
- 只有在缺少初始化成功日志，或存在明确 fail 报错时，才可优先收敛为 TP 侧异常。
