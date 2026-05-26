---
name: mtk-tp-fod-log-analysis
description: "MTK-TP屏下指纹: 分析TP侧FOD录入失败问题，检查kernel_log中fingerprint_status写入、TP模式切换、fod finger down/up上报 | FOD/fingerprint/finger_status/屏下指纹/指纹录入失败/指纹唤醒 | 当用户报告MTK设备屏下指纹录入失败、FOD唤醒失败、FOD按压事件丢失时使用。TP触摸问题走mtk-tp-touch-log-analysis"
funcType: "AI故障分析"
category: "驱动"
---

# MTK TP FOD 异常日志分析

## 适用范围

- **问题类型**：TP 侧屏下指纹无法录入 / FOD 相关异常
- **适用场景**：
  - 屏下指纹项目中指纹无法录入
  - FOD 唤醒失效
  - 指纹录入失败
- **适用芯片平台**：MTK

## 前置条件

分析前需确认以下日志文件可用：

| 日志文件 | 必需性 | 用途 |
|---|---|---|
| `kernel_log` | 必需 | 分析 TP 驱动代码，检查 TP 侧指纹录入节点是否被开启 |

## 问题有效性确认

开始分析前，先确认：

- 项目支持 FOD
- 指纹录入已校准
- 当前 BUG 模块为 TP

## 分析工作流

按以下顺序执行，详细操作参阅 [ANALYSIS_STEPS.md](ANALYSIS_STEPS.md)。

### 步骤1：获取日志
- **目标**：拿到与 TP 侧 FOD 分析直接相关的有效日志
- **操作**：
  - 如果给定的是 JIRA 号、文件夹等非直接 log 文件，先获取日志文件
  - 排除与 TP 领域无关的日志，只保留串口日志、`kernel_log`、Android 日志等
  - 若存在 `mobilelog` 文件夹，优先获取其中的 `kernel_log`
  - 若存在 `mobilelog` 文件夹，开机阶段相关日志优先查看其子目录 `booot_normal`
- **判断**：
  - 获取日志失败 -> 停止分析
  - 获取日志成功 -> 进入步骤2

### 步骤2：日志过滤
- **目标**：缩小到 TP 指纹录入主链路
- **操作**：在 `kernel_log` 中搜索 `touch|fts|cts|gtp|nvt|chsc|ilitek|tcm`，并按原 SOP 补充筛选 `tran_fingerprint_status`
- **判断**：
  - 已获得 TP 及 FOD 关键日志 -> 进入步骤3

### 步骤3：分析日志
- **目标**：确认灭屏 / 亮屏 / 录入场景下 TP 是否正常处理 FOD
- **重点检查**：
  - 灭屏时指纹节点的值是否写入正确
  - 亮屏时是否有指纹按下、抬起事件上报
  - 设置中指纹录入是否有指纹按下、抬起事件上报
- **判断**：
  - 筛选日志中没有指纹按下、抬起事件 -> 可能与 TP 有关
  - 如果有指纹按下、抬起事件 -> 与 TP 无关

## 关键字速查

- 关键词与原始日志示例：参阅 [KEYWORDS.md](KEYWORDS.md)
- 常见问题与根因对照：参阅 [COMMON_ISSUES.md](COMMON_ISSUES.md)
- 典型案例：参阅 [CASES.md](CASES.md)

核心搜索关键字：

```text
kernel_log: touch|fts|cts|gtp|nvt|chsc|ilitek|tcm
supplement: tran_fingerprint_status|fod finger down|fod finger up
```

## 输出格式

按以下模板输出分析结论：

```markdown
# MTK TP FOD 异常日志分析报告

## 基本信息
- 分析时间：[时间]
- 日志来源：[文件列表]
- 问题描述：[用户提供的问题描述]
- 芯片平台：[平台信息，如可确定]

## 分析过程
### 步骤1：获取日志
- 搜索/检查目标：[日志来源、文件完整性]
- 搜索结果：[成功/失败，缺失项摘要]
- 判断结论：[是否满足继续分析条件]

### 步骤2：日志过滤
- 搜索关键字：[本步骤使用的关键字]
- 搜索结果：[匹配摘要]
- 判断结论：[是否进入 TP FOD 主链路]

### 步骤3：分析日志
- 灭屏指纹状态写入：[正常/异常，关键日志]
- 亮屏 FOD 事件上报：[有/无，关键日志]
- 录入场景 FOD 事件上报：[有/无，关键日志]
- 判断结论：[TP 侧结论]

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
- 只有在确认没有 `fod finger down` / `fod finger up` 等关键事件时，才可优先收敛为 TP 侧问题。
- 如果 TP 已存在完整的 FOD 按下 / 抬起事件，应提示继续排查指纹 HAL、framework 或其他非 TP 模块。
