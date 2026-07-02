# 内核稳定性子 skill 路由索引

本表供 `android-kernel-stability-analysis` 总入口使用。所有路径均相对于 **`AI故障分析/内核/`** 目录。

## 1. 平台 × 工具矩阵

| 平台 | 分析子 skill | 需要 `android-kerneldb-extract` | 需要 `android-kerneltne-extract` | 备注 |
|------|--------------|--------------------------------|----------------------------------|------|
| MTK | `android-ke-log-analysis` | 日志含 `*.dbg` 时 | 日志含 `*.tne` 时 | 默认可覆盖 KE / ATF / OCP 等 |
| MTK | `android-hang-log-analysis` | 通常需要 | `0xffffff0c_*.tne`（HANG） | |
| MTK | `android-hwr-hwt-log-analysis` | 通常需要 | `0xffffff0d_*.tne`（HWT） | |
| MTK | `android-bootup-issue-log-analysis` | 通常需要 | 含 `.tne` 时 | 可能同时含 dbg 与 tne |
| MTK | `android-kernel-api-dump-log-analysis` | 通常需要 | 一般不需要 | KernelAPI / EMI MPU |
| 展锐 | `android-unisoc-kernel-crash-log-analysis` | **否**（无 `.dbg`） | 日志含 `*.tne` 时 | 展锐为 **tne 格式、无 db 格式** |

## 2. 现象 → 子 skill（MTK）

| 现象 / 日志锚点 | 子 skill |
|-----------------|----------|
| `不开机` `卡logo` `bootup` `BOOTPROF` `reboot_longkey` `dm-verity` | `android-bootup-issue-log-analysis` |
| `hang detect` `watchdog` `system_server` 阻塞、D 状态线程 | `android-hang-log-analysis` |
| `HWT` `HWR` `hw reboot` `lastpc` `systracker` WDT 超时 | `android-hwr-hwt-log-analysis` |
| `KernelAPI` `EMI MPU` `Plat_Parser` `violation address` | `android-kernel-api-dump-log-analysis` |
| `Kernel panic` `Oops` `KE` `ATF` `__exp_main.txt` `db.fatal` 通用重启 | `android-ke-log-analysis` |

## 3. 现象 → 子 skill（展锐）

| 现象 / 日志锚点 | 子 skill |
|-----------------|----------|
| `dump_report.txt` `extend_last_kmsg` `extend_ylog_buf` `exception_reboot_reason` | `android-unisoc-kernel-crash-log-analysis` |
| 日志含 `*.tne`（展锐内核异常包，**无 `*.dbg`**） | 同上；先按总入口步骤3 安装 `android-kerneltne-extract` 解压 |
| minidump + 目录内 `decompress.py` | 同上（先按子 skill 步骤1解压） |

## 4. `.tne` 前缀与异常类型（MTK AEE 命名）

展锐平台同样使用 **`.tne`** 包，但**不存在 `.dbg`**；文件名前缀可能与下表不同，以实际 `log_root` 扫描为准。解压统一走 **`android-kerneltne-extract`**。

| 文件名前缀 | 异常类型 | 常见关联子 skill（MTK） |
|------------|----------|------------------|
| `0xffffff0c_` | HANG | `android-hang-log-analysis` |
| `0xffffff0d_` | HWT | `android-hwr-hwt-log-analysis` |
| `0xffffff04_` | KE | `android-ke-log-analysis` |
| `0xffffff15_` | OCP_REBOOT | `android-ke-log-analysis` |

## 5. GitLab 工具安装路径对照

源仓库：<http://gitlab.transsion.com/lq/skills.git>

| 工具 skill | 仓库内路径 | 安装目标 |
|------------|------------|----------|
| `android-kerneldb-extract` | `skills/AI故障分析/内核/android-kerneldb-extract` | `.cursor/skills/android-kerneldb-extract` |
| `android-kerneltne-extract` | `skills/AI故障分析/内核/android-kerneltne-extract` | `.cursor/skills/android-kerneltne-extract` |
| `android-analysis-shared` | `skills/AI故障分析/内核/android-analysis-shared` | `.cursor/skills/android-analysis-shared` |

## 6. 协作顺序示意

```text
用户问题
  → android-kernel-stability-analysis（本总入口）
      → 平台？ MTK / 展锐
      → 现象？ 选 1 个分析子 skill
      → [MTK] log_root 含 .dbg / .tne？
          → .dbg：安装 kerneldb-extract（仅 MTK）
          → .tne：安装 kerneltne-extract（MTK / 展锐）
      → [展锐] 仅 .tne，无 .dbg；禁止 kerneldb-extract
      → 打开分析子 skill，执行提取脚本 + AI 分析 + 报告
```
