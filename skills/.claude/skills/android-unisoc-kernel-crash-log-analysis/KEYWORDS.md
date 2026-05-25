# 关键字与日志示例参考

本文档根据《展锐平台内核死机问题分析SOP》**术语定义**与**分析流程**整理，便于在 dump 包与内核日志中检索。

## 关键词列表（建议 grep / 搜索）

竖线分隔，可按需拆分为多条命令：

```
dump_report.txt|reason|exception_reboot_reason|exception_panic_reason|exception_stack_info|extend_last_kmsg|extend_ylog_buf|last_kmsg.log|last_kmsg.txt|minidump|decompress.py|Kernel panic|not syncing|BUG|Oops|backtrace|pc|lr|watchdog|wdt|cm4_watchdog_timeout|extend_runqueue|extend_task_stats|addr2line|gdb|trace32|vmlinux
```

## 术语定义（SOP 原文）

| 术语 | 含义 |
|------|------|
| KE | Kernel Exception，内核异常 |
| ATF | Arm Trusted Firmware，ARM 可信固件 |
| SSPM | System Security Processor Manager，系统安全处理器管理器 |
| EMI | External Memory Interface，外部内存接口 |
| LPM | Low Power Mode，低功耗模式 |
| DB | Debug Bundle，调试数据包 |

## dump_report.txt 关注字段（解读要点）

- **`reason` / `exception_reboot_reason`**：用于**异常类型归类**（如 KE-Oops/Panic、watchdog_timeout 等）；`exception_panic_reason` 等为更细异常信息。
- **`exception_stack_info`**：异常时的**调用栈**，与 backtrace 分析直接相关。

*注：SOP 未给出固定日志原文示例块；实际分析时应在用户提供的 `dump_report.txt` 中截取包含上述字段的片段作为证据。*

## 文件角色与检索关系

| 文件/场景 | 检索/动作要点 |
|-----------|----------------|
| minidump | 目录下存在 `decompress.py` 时须先执行解压 |
| last_kmsg.txt / 相关 kmsg | 搜索 `watchdog`、`wdt` 等，辅助 watchdog 流程分析 |
| extend_runqueue、extend_task_stats、minidump 对应 extend_* | 结合进程信息辅助分析 |
| 符号与镜像 | 准确版本号（Jira / Build Info / display.id）→ 对应归档中的 **vmlinux** 与 **ko** |

## 分析流程中的关键字使用（与 SOP 4.2 对齐）

1. **归类阶段**：优先使用 `dump_report.txt` 中 **reason / exception_reboot_reason**。
2. **主证据**：**backtrace**、**pc**、**lr**、**kernel offset**、**BUG**、**oops**、**panic**。
3. **Watchdog**：**watchdog**、**wdt**；reason 为 **cm4_watchdog_timeout** 时按 SOP 转交展锐侧。
4. **映射**：对命中地址使用匹配 **vmlinux/ko** + **addr2line / gdb / trace32**。
