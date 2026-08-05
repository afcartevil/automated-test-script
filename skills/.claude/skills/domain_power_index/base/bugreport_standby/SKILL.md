---
name: base_bugreport_standby
description: Bugreport 待机统一能力：耗电排行 + kernel/partial 持锁统计（统一分块策略）。
---

## 适用场景

在解压后的 bugreport 大文本上，统一完成待机相关解析：
- `Estimated power use (mAh)`
- `All kernel wake locks`
- `All partial wake locks`

## 核心约束（当前方案）

- 数据源仅限 bugreport 文本，不与 kernel 日志混用。
- 大文件按约 200k 行/块分段读取，分块规则仅在本能力维护。
- 结果需与 `base_kernel_standby` 可拼装，避免术语混淆（R12 唤醒 != partial wakelock 持锁）。
- 目录输入时会扫描 `bugreports/` 下**所有 bugreport 候选文件**（包括常见的 `bugreport-*.tmp`、`bugreport-*.txt`），自动忽略 `dumpstate_log*.txt` / `dumpstate-stats.txt` 这类摘要文件，并优先选取**真正包含有效 bugreport 内容**的文件作为分析源。
- 输入应为**已提前解压好的 bugreport 文本**；本能力不负责从 zip 中读取或解压。

## 输出要求（供 domain 编排复用）

- `bugreport_summary`：耗电模块/UID 排名摘要
- `top_locks`：kernel locks + partial locks 的 Top 项（时长/次数/包名/UID）
- `power_rank`：`Estimated power use` 关键条目
- `raw_evidence`：每类至少 1 段可引用原文

## 执行方式（建议）

```bash
python scripts/bugreport_standby.py [options]
```

## 参数说明

| 参数 | 作用 | 生效条件 |
|---|---|---|
| `-d DIR`, `--directory DIR` | 指定已解压好的 bugreport 目录；脚本会扫描目录下全部 bugreport 候选文件并自动选择最有效的内容源 | 与 `--file`、`--stdin` 互斥，三选一 |
| `--file FILE` | 指定单个 bugreport 文本文件 | 与 `-d/--directory`、`--stdin` 互斥，三选一 |
| `--stdin` | 从标准输入读取 bugreport 内容 | 与 `-d/--directory`、`--file` 互斥，三选一 |
| `--format {text,json}` | 输出格式：`text`（默认）或 `json` | 可选 |
| `--field FIELD` | JSON 输出时仅返回 `summary` 字段，可重复 | 仅在 `--format json` 生效 |

## 输出说明

脚本输出包含两部分，格式与 `base_kernel_standby` 一致：

1) **详细明细**（便于人工快速查看）
- `Estimated power use (mAh)` Top 项
- `All kernel wake locks` Top 项
- `All partial wake locks` Top 项

2) **结构化分析摘要（供下游 SKILL 输入）**

```text
=== 结构化分析摘要(供下游SKILL输入) ===
[META]
analysis_start=<MM-DD HH:MM:SS or empty>
analysis_end=<MM-DD HH:MM:SS or empty>
analysis_duration_h=

[THRESHOLD]
standby_26m_off_pct_threshold=70
hardware_discharge_abnormal_threshold_ma=3000

[SUMMARY]
bugreport_summary=<power_items=...; kernel_lock_items=...; partial_lock_items=...>
top_locks=<kernel=...; partial=...>
power_rank=<Top3=...; total=... or No>
raw_evidence=<Yes/No>

[STATS]
power_rank_count=<int>
kernel_lock_count=<int>
partial_lock_count=<int>
power_rank_top=<Top3=...; total=... or No>
kernel_lock_duration_top=<Top3=...; total=... or No>
partial_lock_duration_top=<Top3=...; total=... or No>
evidence_power_rank_lines=<int>
evidence_kernel_lock_lines=<int>
evidence_partial_lock_lines=<int>
```

## 调用建议

当待机场景需要完整结论时，建议按链路调用：
`base03 -> base09 -> base11 -> base_kernel_standby -> base05/06 -> base07/08`
