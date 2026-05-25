# 常见问题与现象对照

原 SOP 未单独设置「第五章」表格，下表由 **SOP 4.3 分支**与 **4.2 步骤逻辑**整理，便于快速对照。

| 序号 | 问题现象 / 分支 | 日志特征（检索方向） | 说明 / 处理要点 |
|------|------------------|----------------------|-----------------|
| 1 | KE-Oops/Panic | panic / BUG / Oops；`exception_stack_info`、backtrace | 自下而上找首个业务函数；核对寄存器与 fault address |
| 2 | watchdog_timeout 且 reason 为 cm4 | `reason` / `exception_reboot_reason` 指示 **cm4_watchdog_timeout** | 按 SOP：**提交展锐**进行分析 |
| 3 | watchdog_timeout（一般） | **last_kmsg.txt** 中 **watchdog**、**wdt** 等 | 分析喂狗流程；可结合 extend_runqueue、extend_task_stats |
| 4 | 符号/结论不可靠 | 调试包版本与符号表版本不一致 | **符号不匹配时结论无效**；先对齐 Jira/Build Info/display.id |
| 5 | minidump 未解压 | 目录存在 **decompress.py** 但未执行 | 须先解压再归类与证据提取 |

## 详细说明

### KE-Oops/Panic

**日志特征**：出现典型内核 panic / BUG / Oops 描述；`dump_report.txt` 中可归入相应异常类型；栈信息见 `exception_stack_info`。

**处理**：确认 panic 标志后，从 backtrace 自下而上定位业务函数，再结合寄存器与 fault address。

### watchdog_timeout

**日志特征**：`dump_report.txt` 中 reason 相关字段；**last_kmsg.txt** 中 watchdog / wdt 关键字。

**处理**：若判断为 **cm4_watchdog_timeout**，按 SOP 转交展锐；否则结合喂狗链路与调度/任务统计文件深入分析。
