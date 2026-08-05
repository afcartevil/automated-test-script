---
name: base_networkinfo
description: 蜂窝网络信息
---
## 适用场景
使用 `networkinfo.py` 获取网络信息，支持以下功能：

- 统计网络情况
- 支持按时间范围筛选
- 自动解析工作区内 `radio_log_*` 路径（优先 `converted/APLog/`）

## 前置条件

- 日志包须含 `radio_log_*` 文件（通常在 APLog 中，而非 NTLog）
- 无 radio_log 时本 skill **skip**，由 flow 在结论中标注「网络制式信息缺失」

## 执行方式

在技能目录下执行（或使用仓库内脚本的绝对路径）：

```bash
python networkinfo.py [options]
```

## 参数说明

| 参数 | 作用 | 生效条件 |
|---|---|---|
| `-d DIR`, `--directory DIR` | 工作区根、`converted/`、`converted/APLog/` 或含 `radio_log_*` 的目录 | 必须指定 |
| `-t START END`, `--time START END` | 开始时间和结束时间（格式：YYYY-MM-DD HH:MM:SS） | 可选 |
| `--fallback {none,nearest,full}` | 时间窗无 ServiceState/PS 记录时的回退策略；flow 高功耗窗分析推荐 `nearest` | 可选，默认 `none` |
| `--probe` | 仅探测 `radio_log_*` 是否就绪（JSON） | 可选 |
| `--format {text,json}` | 输出格式 | 可选，默认 `text` |

## 使用示例

```bash
# 探测 radio_log 是否可用（flow 步骤 7 建议先执行）
python networkinfo.py -d <repo>/temp/<DATE>/<KEY> --probe

# 分析高功耗窗口（目录可传工作区根，脚本自动定位 APLog）
python networkinfo.py -d <repo>/temp/<DATE>/<KEY> \
  -t "2025-12-03 07:17:24" "2025-12-03 07:38:11" \
  --fallback nearest --format json

# 全量统计
python networkinfo.py -d <repo>/temp/<DATE>/<KEY>/converted/APLog
```

## 路径解析（`scripts/radio_log_paths.py`）

优先级：`converted/APLog/` → `converted/` → 输入目录递归。

## 输出说明

执行脚本后，会输出以下格式的信息：

```
=== 网络信息分析结果 ===
开始时间: 2026-03-04 17:42:14, 结束时间: 2026-03-05 02:09:57

卡1 ([PHONE0]) - MCC: 510, MNC: 10
卡2 ([PHONE1]) - MCC: None, MNC: None

卡1 PS域状态变化次数: 8
卡1 CS域状态变化次数: 7
卡2 PS域状态变化次数: 0
卡2 CS域状态变化次数: 0
ServiceState记录数: 61
PS cellular记录数: 61

===== ServiceState详细信息 =====
时间              CS状态                 PS状态                 双工模式            带宽                   网络选择            网络制式                 CA
------------------------------------------------------------------------------------------------------------------------------------------------------
03-04 17:26:29  0(IN_SERVICE)        0(IN_SERVICE)        1               [10000]              false(automatic) 14(LTE)              false
===== PS cellular详细信息 =====
时间              PS状态                漫游状态       网络制式      rejectCause       小区            band
-------------------------------------------------------------------------------------------------------------------   
03-04 17:26:29  HOME                 NOT_ROAMING     LTE             0               88              [8]
```

`--probe` 或缺失 radio_log 时 JSON 示例：

```json
{"scan_dir": ".../converted/APLog", "radio_log_count": 0, "radio_log_files": [], "ready": false}
```
