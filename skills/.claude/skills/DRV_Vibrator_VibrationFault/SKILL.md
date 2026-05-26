---
name: "DRV_Vibrator_VibrationFault"
description: "针对MTK平台线性马达部分场景无振动或波形返回错误问题（包含全场景无振动、单场景无振动有波形返回、有振动但无波形返回/波形错误等场景），通过分析kernel_log中haptic/richtap马达驱动是否正常工作、sys_log中应用是否通过TranVibratorManagerInternal下发HE文件及HAL层RichTapVibratorService服务状态、main_log中HE文件是否存在及安卓原生振动链路佐证日志（如LED trigger、SystemVibratorManager vibrate），定位问题根因（HAL层异常/HE文件缺失/应用未适配）并输出分析结论。当用户提供包含vib/haptic/richtap/TranVibratorManagerInternal/RichTapVibratorService/LED trigger等关键字的日志，且JIRA问题模块为(Drv) Vibrator并涉及线性马达无振动或波形返回错误时使用。"
funcType: "AI故障分析"
category: "驱动"
---

# MTK 线性马达无振动或波形返回错误日志分析

## 适用范围

- **问题类型**：线性马达部分场景无振动 / 波形返回错误
- **适用场景**：
  - 线性马达某个场景没有振动
  - 线性马达某个场景的振动波形返回错误
  - 全场景无振动
  - 应用下发振动但无 HE 波形返回
- **适用芯片平台**：MTK

## 问题有效性确认

开始分析前，先确认：

- 平台为 MTK
- 项目为线性马达
- 已获取相关 log（kernel_log / main_log / sys_log）
- JIRA 问题模块为 `(Drv) Vibrator`

## 前置条件

分析前需确认以下日志文件可用：

| 日志文件 | 必需性 | 用途 |
|---|---|---|
| `kernel_log` | 必需 | 检查马达驱动是否正常工作、是否正确处理 he 效果文件 |
| `sys_log` | 必需 | 检查场景是否下发正确的 he 文件 |
| `main_log` | 必需 | 检查 he 文件是否存在 |

## 分析工作流

按以下顺序执行，详细操作参阅 [ANALYSIS_STEPS.md](ANALYSIS_STEPS.md)。

### 步骤1：获取日志
- **目标**：拿到与马达振动分析直接相关的有效日志
- **操作**：
  - 如果给定的是 JIRA 号、文件夹等非直接 log 文件，先获取日志文件
  - 排除与马达驱动无关的日志文件，只保留串口日志、`kernel_log`、Android 日志等
  - 若存在 `mobilelog` 文件夹，优先获取其中的 `kernel_log`、`main_log`、`sys_log`
  - 若存在 `mobilelog` 文件夹，开机阶段相关日志优先查看其子目录 `booot_normal`
- **判断**：
  - 获取日志失败 -> 停止分析
  - 获取日志成功 -> 进入步骤2

### 步骤2：日志过滤
- **目标**：筛选马达振动分析的关键日志
- **操作**：
  - 在 `kernel_log` 中搜索：`haptic`、`vib`
  - 在 `main_log` / `sys_log` 中搜索：`vib`、`haptic`、`richtap`
- **判断**：
  - 筛选成功 -> 进入步骤3

### 步骤3：分析 sys_log 日志
- **目标**：确认 framework 层是否正确下发 HE 文件
- **场景 A：JIRA 标题说的是"无振动"**
  - 根据 JIRA 信息找出有问题的下发的 HE 文件名和应用
  - 确认 HAL 层 `RichTapVibratorService` 服务是否正常
  - 如果正常，进入步骤4，分析 main_log，确定是否有该 HE 文件
- **场景 B：JIRA 标题说的是"无波形返回"**
  - 根据 JIRA 信息找出有问题的下发的 HE 文件名和应用
  - 分析应用的本次振动是否走 `TranVibratorManagerInternal` 调用 HE 文件（`TranVibratorManagerInternal: vibrate: <文件名>.he`）
  - **若问题场景复现时间窗口内未出现上述 HE 下发日志，即可判定走的是安卓原生振动链路（无 HE 波形）**；main_log 用于抓取佐证（如 `SystemVibratorManager vibrate`、`LED trigger`），并非唯一判定条件

### 步骤4：分析 main_log 日志
- **目标**：确认 HE 文件存在性与振动驱动通路（含原生链路佐证）
- **场景 A：JIRA 标题说的是"无振动"**
  - 检查是否有"找不到应用下发 he 文件"的报错（`java.io.FileNotFoundException`）
- **场景 B：JIRA 标题说的是"无波形返回"**
  - 若在步骤3已判定未走 `TranVibratorManagerInternal` HE 下发，步骤4着重抓取 `SystemVibratorManager vibrate`、`Vibrator: Vibrator using LED trigger` 等日志作为佐证（有则增强置信度；无亦可基于「无 HE 下发」单独下结论，需在报告中注明日志佐证不足）

## 关键字速查

- 关键词与原始日志示例：参阅 [KEYWORDS.md](KEYWORDS.md)
- 常见问题与根因对照：参阅 [COMMON_ISSUES.md](COMMON_ISSUES.md)
- 典型案例：参阅 [CASES.md](CASES.md)

核心搜索关键字：

```text
kernel_log: haptic|vib
main_log / sys_log: vib|haptic|richtap
HAL 异常关键句: RichTapVibratorService: aac richtap doVibratorStop fail.
HE 缺失关键句: java.io.FileNotFoundException: .../vibrates/*.he
原生链路佐证: SystemVibratorManager vibrate | Vibrator: Vibrator using LED trigger（可选，增强置信度）
```

## 输出格式

按以下模板输出分析结论：

```markdown
# MTK 线性马达无振动或波形返回错误日志分析报告

## 基本信息
- 分析时间：[时间]
- 日志来源：[文件列表]
- 问题描述：[用户提供的问题描述，区分"无振动"或"无波形返回"]
- 芯片平台：MTK
- JIRA 模块：(Drv) Vibrator

## 分析过程
### 步骤1：获取日志
- 搜索/检查目标：[kernel_log、main_log、sys_log 完整性]
- 搜索结果：[成功/失败，缺失项摘要]
- 判断结论：[是否满足继续分析条件]

### 步骤2：日志过滤
- 搜索关键字：[本步骤使用的关键字]
- 搜索结果：[匹配摘要]
- 判断结论：[是否进入马达主链路]

### 步骤3：分析 sys_log
- 应用下发 HE 文件：[HE 文件名、pkg、usage]
- TranVibratorManagerInternal 调用：[有/无]
- HAL 层 RichTapVibratorService 状态：[正常/异常，关键日志]
- 判断结论：[framework 层结论]

### 步骤4：分析 main_log
- HE 文件存在性：[找到/未找到，关键日志]
- 振动驱动通路：[richtap HE / 原生（未走 Tran HE 下发）/ LED trigger 等佐证]
- 判断结论：[main_log 侧结论]

## 分析结论
- 问题根因：[根因描述，对应 COMMON_ISSUES 中的某一类]
- 证据摘要：[支持结论的关键日志行]
- 置信度：[高/中/低]
- 建议措施：[后续处理建议，如配置 HE 文件、检查 HAL 算法库、应用同事适配等]
```

## 参考信息

- 关键字与日志示例：参阅 [KEYWORDS.md](KEYWORDS.md)
- 常见问题对照：参阅 [COMMON_ISSUES.md](COMMON_ISSUES.md)
- 典型案例参考：参阅 [CASES.md](CASES.md)

## 约束

- 不要假装看过未提供的日志。
- 缺少 `kernel_log`、`main_log` 或 `sys_log` 中任一时，需说明缺失项可能影响的结论环节。
- 只有在 sys_log 中看到 `RichTapVibratorService: aac richtap doVibratorStop fail.` 才可判定为 HAL 层服务异常。
- 只有在 main_log 中看到 `FileNotFoundException: .../*.he` 才可判定为 HE 文件缺失。
- **判定安卓原生振动链路（无 HE 波形）**：问题场景复现时间窗口内，`sys_log`/`main_log` 均未出现对应应用的 `TranVibratorManagerInternal: vibrate: *.he`，即可判定未走 HE 下发，属于安卓原生振动通路范畴；`Vibrator: Vibrator using LED trigger`、`VibratorManager: [SystemVibratorManager vibrate]` 等为**辅助佐证**，有则提高置信度，无则需在报告中说明仅凭「无 Tran HE 下发」得出结论。
- 不要将"有振动 + 无 HE 波形"与"无振动 + 有 HE 波形"两类问题混淆，需先按 JIRA 标题选择分支。
