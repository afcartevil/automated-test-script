# 功耗待机 — 关键字 / 检索备忘（`rg` / 文本搜索）

**不是证据**：下列 pattern 仅帮助 **定位文件与行**；表格里的标签名、包名、寄存器如何解读，**一律以命中行的原文 + Jira + SOP 可追溯段落为准**，**禁止**根据「通常」「常见」补造未在日志中出现的结论。

在 **已锚定时间窗** 的前提下对 **工作区内** 日志检索；全库盲搜仅作发现手段，结论必须回到窗口内按时间复核（与 `bug-analysis` 一致）。

***

## bugreport（或解压文本）

| 目标 | 建议 pattern / 片段 |
|------|---------------------|
| 耗电排行 | `Estimated power use` |
| 用户态持锁 | `All partial wake locks`、`Wake lock` |
| 内核持锁 | `All kernel wake locks`、`Kernel Wake lock` |
| UID 耗电 | `UID u`、`: apps:` 行 |

## kernel / APLog kernel

| 目标 | 建议 pattern |
|------|----------------|
| 进入/退出休眠 | `PM: suspend entry`、`PM: suspend exit`、`s2idle` |
| SPM 唤醒 | `suspend wake up by`、`SPM] wake up by`、`\[SPM\]` |
| 寄存器字段 | `r12`、`r12_ext`、`r13`、`debug_flag`、`26M_off_pct` |
| 持锁阻碍休眠 | `Pending Wakeup`、`aborting suspend`、`active wakeup source` |
| 26M / PLL | `blocked by`、`unexpected unclosed pll` |
| audio / 耳机 | `suspend warning`、audio、`pcm_flag` |
| CPU 排行 | `Cpus Usage`、`PERF.*Usage`、`Usage`（结合灭屏时段） |
| 射频强度 | `rssi` |
| 电池采样 | `healthd`、`battery l=` |
| connsys / modem | `WMT-CONSYS`、`mtk_wmt_resume`、`md_slp_duration`、`mtk_wcn_consys_sleep_info_read_all_ctrl` |
| SCP | `scp_sleep_cnt`、`mt_scp_dump` |

## main / system / events（按窗口）

| 目标 | 建议 pattern |
|------|----------------|
| 电量点 | `battery_level` |
| Alarm 归属 | `AlarmManager`、`Native set alarm`、`alarm`、包名 |
| Job / 后台 | `JobScheduler`（若现象相关） |

## netlog / pcap

- 在 **Wireshark** 内按测试时段过滤 **应用/TCP 会话**；与 kernel 中 **R12_CONN2AP**、**R12_AP2AP_PEER / CLDMA** 出现时刻对齐。

***

## 使用提示

- **优先相对路径**：报告里写 `Evidence: \`path/to/file\` L…`。  
- 中文路径在 PowerShell 下注意引号；大文件配合 **`SKILL.md`** 中的分段阅读策略。
