---
name: android-unisoc-kernel-crash-log-analysis
description: 针对展锐（Unisoc）平台内核死机与整机重启 dump 问题（含 KE-Oops/Panic、watchdog_timeout 等），通过分析 dump_report.txt、extend_last_kmsg、extend_ylog_buf、last_kmsg.log、last_kmsg.txt 等中的 reason、exception_reboot_reason、backtrace、watchdog 等关键信息完成归类、时间线、符号映射与根因判断。当用户提供展锐平台重启 dump、内核异常日志且需按 SOP 输出分析结论或整理 Jira 证据时使用。
---

# 展锐平台内核死机问题分析（日志）

## 适用范围

- **问题类型**：展锐平台内核死机（KE）、整机重启 dump、内核异常重启分析。
- **适用场景**：
  - 整机重启 dump 包分析；
  - KE-Oops/Panic、watchdog_timeout 等异常归类与证据链建立；
  - 需要输出 Jira 报告要素与符号表映射结论时。
- **适用芯片平台**：展锐（Unisoc）平台。

**来源文档（飞书 Wiki）**：`https://transsioner.feishu.cn/wiki/GPWtwlkf7i2yZqko9C5csmkmn7f`（节点 token：`GPWtwlkf7i2yZqko9C5csmkmn7f`）。

## 前置条件

分析前尽量确认以下文件可用（优先级见 `ANALYSIS_STEPS.md` 第 4.1 节）：

| 日志/文件 | 必需性 | 用途 |
|-----------|--------|------|
| dump_report.txt | 必需（优先） | 异常分类，`reason` / `exception_reboot_reason` 等 |
| extend_last_kmsg | 必需 | 与 dump_report 等建立证据链 |
| extend_ylog_buf | 必需 | 同上 |
| last_kmsg.log | 必需 | 同上 |
| extend_runqueue、extend_task_stats、xxx_minidump_extend_runqueue、xxx_minidump_extend_task_stats | 可选（场景化补充） | 进程/调度相关信息 |
| minidump 场景下的 decompress.py | 条件必需 | minidump 时需执行解压脚本 |
| vmlinux、匹配版本的 ko | 条件必需 | addr2line / gdb / trace32；版本不匹配则结论无效 |

## 问题有效性确认

在展开深度分析前确认：

1. 问题属于 **展锐平台整机重启 dump** 场景（与 SOP 适用范围一致）。
2. 已获取 **准确软件版本**（Jira 影响版本 / Build Info / display.id 等），以便符号表与内核镜像匹配。
3. 若为 **minidump**：日志目录存在 `decompress.py` 时，须先执行解压后再分析。

## 分析工作流

下文为概述；逐步操作、判断表与日志示例详见各引用文件。

### 步骤1：文件预处理

- **目标**：确认日志是否为 minidump，并完成必要解压。
- **操作**：检查是否存在 `decompress.py`，存在则按脚本解压后再分析。
- **参阅**：[ANALYSIS_STEPS.md](ANALYSIS_STEPS.md)「步骤1」。

### 步骤2：异常归类

- **目标**：依据 `dump_report.txt` 中 `reason`、`exception_reboot_reason` 等字段划分异常类型（如 KE-Oops/Panic、watchdog_timeout 等）。
- **操作**：读取 `exception_reboot_reason`、`exception_panic_reason`、`exception_stack_info` 等字段；结合调用栈信息。
- **参阅**：[ANALYSIS_STEPS.md](ANALYSIS_STEPS.md)「步骤2」、[KEYWORDS.md](KEYWORDS.md)。

### 步骤3：时间线对齐

- **目标**：锁定异常发生时间点，建立「异常前操作 → 异常触发 → 重启/恢复」时间线。
- **参阅**：[ANALYSIS_STEPS.md](ANALYSIS_STEPS.md)「步骤3」。

### 步骤4：主证据定位

- **目标**：按优先级搜索 backtrace、pc、lr、kernel offset、BUG、oops、panic 等，定位首个业务相关栈帧。
- **参阅**：[ANALYSIS_STEPS.md](ANALYSIS_STEPS.md)「步骤4」、[KEYWORDS.md](KEYWORDS.md)。

### 步骤5：代码映射

- **目标**：使用匹配版本的 vmlinux/ko 做 addr2line 或 gdb/trace32，形成「日志地址 → 代码位置」闭环。
- **参阅**：[ANALYSIS_STEPS.md](ANALYSIS_STEPS.md)「步骤5」。

### 步骤6：根因判断

- **目标**：区分访问越界、空指针、死锁、内存压力、总线超时、权限/配置不匹配等方向，给出置信度与证据边界。
- **参阅**：[ANALYSIS_STEPS.md](ANALYSIS_STEPS.md)「步骤6」。

### 分支补充（SOP 4.3）

- **KE-Oops/Panic**：确认 panic/BUG/Oops 标志；自下而上解析 backtrace。
- **watchdog_timeout**：区分 reason；若为 `cm4_watchdog_timeout` 须提交展锐分析；结合 `last_kmsg.txt` 中 watchdog/wdt 等关键字；必要时结合 extend_runqueue、extend_task_stats。
- **参阅**：[ANALYSIS_STEPS.md](ANALYSIS_STEPS.md)「4.3」、[COMMON_ISSUES.md](COMMON_ISSUES.md)。

## Jira 报告要素（摘要）

完整条目见 [ANALYSIS_STEPS.md](ANALYSIS_STEPS.md) 第五节对应原文；输出分析报告时应覆盖：问题概述、平台信息、异常时间、崩溃 CPU、关键异常描述、关键证据、初步结论、建议行动项等。

## 关键字速查

完整关键字与字段说明见 [KEYWORDS.md](KEYWORDS.md)。

核心检索词示例：`dump_report.txt`|`reason`|`exception_reboot_reason`|`exception_stack_info`|`extend_last_kmsg`|`last_kmsg`|`watchdog`|`wdt`|`backtrace`|`oops`|`panic`|`BUG`

## 输出格式

按以下模板输出分析结论：

### 展锐平台内核死机（KE）日志分析报告

#### 基本信息

- **分析时间**：{当前时间}
- **日志来源**：{用户提供的日志文件列表}
- **问题描述**：{用户描述的现象}
- **芯片/平台**：展锐（若日志或项目中可确认）

#### 分析过程

**步骤 N：{步骤名称}**

- **搜索目标**：在 {文件} 中检索 `{关键字}`
- **搜索结果**：{命中摘要或未发现}
- **关键日志**：
  ```
  {关键行原文摘录}
  ```
- **步骤结论**：{本步结论}

（覆盖已执行的预处理、归类、时间线、证据、映射、根因等步骤。）

#### 分析结论

- **问题根因**：{结论}
- **证据摘要**：{关键日志与映射结果}
- **置信度**：{高/中/低及依据}
- **建议措施**：{后续建议；若涉及 cm4_watchdog_timeout 等按 SOP 注明协同方}

#### 参考信息

- **关键字与字段**：参阅 [KEYWORDS.md](KEYWORDS.md)
- **分支与现象对照**：参阅 [COMMON_ISSUES.md](COMMON_ISSUES.md)
- **典型案例**：参阅 [CASES.md](CASES.md)（原文 SOP 未附案例时说明「无独立案例章节」）
