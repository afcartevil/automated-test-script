# 详细分析步骤

以下内容忠实整理自《展锐平台内核死机问题分析SOP》第 **4**、**5**、**6** 节结构（原文标题编号保留）。

## 4. 分析流程（总述）

以下内容用于统一 KE 问题的「所需文档—分析流程—分析步骤—关键信息」输出口径。

### 4.1 所需文档与优先级

1. **必需文件**：`dump_report.txt`、`extend_last_kmsg`、`extend_ylog_buf`、`last_kmsg.log`。优先用 `dump_report.txt` 完成异常分类，再用 `extend_last_kmsg`、`extend_ylog_buf`、`last_kmsg.log` 建立证据链。
2. **场景化补充**：`extend_runqueue`、`extend_task_stats`、`xxx_minidump_extend_runqueue`、`xxx_minidump_extend_task_stats`。
3. **符号表准备**：先确认准确版本号（Jira 影响版本 / Build Info / display.id），再从对应归档提取 **vmlinux** 与相关 **ko**；**符号不匹配时结论无效**。

### 4.2 分析流程（步骤 1～6）

**步骤1（文件预处理）**：判断日志是否是 minidump；若是 minidump，日志目录下存在 `decompress.py`，需要执行该脚本解压日志。

**步骤2（异常归类）**：依据 `dump_report.txt` 中 `reason`、`exception_reboot_reason` 字段判断异常类型，将问题分到 KE-Oops/Panic、watchdog_timeout 等；`exception_reboot_reason`、`exception_panic_reason` 等字段是异常的详细信息，`exception_stack_info` 是异常时调用栈。

**步骤3（时间线对齐）**：锁定异常发生时间点，建立「异常前操作 -> 异常触发 -> 重启/恢复」时间线，避免跨时段误判。

**步骤4（主证据定位）**：按优先级搜索 backtrace、pc、lr、kernel offset、BUG、oops、panic 关键字，定位首个业务相关栈帧（排除公共异常框架栈）。

**步骤5（代码映射）**：使用匹配 vmlinux/ko 做 addr2line 或 gdb/trace32 映射，得到函数、文件与行号，形成「日志地址 -> 代码位置」闭环。

**步骤6（根因判断）**：区分访问越界、空指针、死锁、内存压力、总线超时、权限/配置不匹配等根因方向，给出置信度和证据边界。

### 4.3 分支分析步骤

#### 4.3.1 KE-Oops/Panic

确认「Kernel panic - not syncing」/ BUG / Oops 标志；从 **backtrace** 自下向上找首个业务函数，再核对寄存器与 fault address。

#### 4.3.2 watchdog_timeout

1. 区分 **reason** 原因；若为 **`cm4_watchdog_timeout`**，则需要提交展锐进行分析。
2. 查询 **last_kmsg.txt** 是否有关键字「watchdog」、「wdt」等，进一步分析 watchdog 喂狗流程。
3. 如有需要可从 **extend_runqueue**、**extend_task_stats** 等文件中结合进程信息进一步分析。

---

## 5. Jira 报告内容要求（SOP 原文条目）

为方便按本 SOP 开展分析、定位与闭环，Jira 问题报告应至少包含以下要素：

- **问题概述**：异常分类、崩溃 CPU/线程、关键函数（含地址映射结果）、触发场景与时间线。
- **平台信息**：芯片型号、软件版本（含 build 类型）、机型/项目代号等。
- **异常时间信息**：异常发生时刻（开机秒数或绝对时间）、关键操作时间线。
- **崩溃 CPU**：异常发生的 CPU 编号及必要时其他 CPU 状态摘要。
- **关键异常描述**：异常分类、崩溃 CPU/线程、关键函数（含地址映射结果）、触发场景与时间线。
- **关键证据**：调用栈、寄存器/反汇编要点、相关日志摘录、已收集 DB 文件清单；关键日志原文（文件名+关键行）+ 调用栈链路 + 符号映射结果（vmlinux/ko 版本信息）。
- **初步结论**：根因方向（高/中/低置信度）+ 已证实/待验证边界、分析进程的调用栈、确定崩溃发生的具体函数。
- **建议行动项**：下一步需要的符号文件、实验、跨团队协同与优先级；补日志、复现、模块协同/提 CR。

---

## 6. 版本历史（文献）

- **V1.0**：2026-05-12 初始版本
