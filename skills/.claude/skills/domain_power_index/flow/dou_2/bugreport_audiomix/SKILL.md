---
name: flow_power_bugreport_audiomix
description: >-
  从 bugreport txt 解析 Battery History 中 AudioMix longwake/wake_lock，
  输出持锁时间轴（TXT/HTML）、持锁方、时长分桶与 Battery Stats 汇总。
  DOU 流程第 9 步；归属 flow/dou_2。高/低功耗均须跑 wakelock。
---

# flow_power_bugreport_audiomix — Bugreport AudioMix 持锁时间轴

## 在 DOU 流程中的位置

| 顺序 | 步骤 | 入口 |
|------|------|------|
| 8 | HTML 渲染 | `tool1_2/run_final_html.py` |
| **9** | **本 skill：AudioMix + 全部 Long Wakelock** | **`tool1_2/run_bugreport_audiomix.py <high> --low <low>`** + **`run_bugreport_longwake.py <high> --low <low>`** |
| 10 | 应用下载/安装检测 | `tool1_2/run_app_download.py` |

主 skill 见 `../SKILL.md` §11。

## 适用场景

- DOU / 功耗分析中排查 **AudioMix 异常持锁**（后台播放、音频未释放等）
- 输入为高/低功耗根目录（自动搜 bugreport）或显式 bugreport 路径
- **高/低功耗均需跑 wakelock**；HTML 报告默认折叠展示两侧结果

## 输入

| 项 | 说明 |
|----|------|
| DOU 标准 | `<high>` + **`--low <low>`（推荐必传）**；未传时回退 `dou_prepare` → `scene_compare` → `power_analysis` 的 `low` |
| 低层调试 | bugreport 目录或 `bugreport-*.txt` 文件 |
| 典型位置 | `<side>/phone_logs/mobile_log*/bugreports/bugreport-*.zip` → 主 txt → `bugreport_main.txt` |

## 低功耗必须跑（勿只传 high）

- HTML 报告「Long Wakelock」分 **高功耗 / 低功耗** 两块；low 摘要在 `<low>/bugreport_*_result.json`。
- 若命令只有 `$high` 且无法从 JSON 解析到 `low`，脚本**只跑 high** 并 WARN → 看板低功耗块为空。
- 手工路径 DOU（无 JIRA prepare）**务必** `--low $low`。

## Bugreport 解压

统一由 `scripts/dou_unzip.py` 处理：

```text
mobile_log*.zip     →  <同目录>/<zip 去后缀>/
bugreport*.zip      →  同目录写出 bugreport_main.txt（只抽主 txt，避开 UNC 上 FS/ 长路径）
```

1. 先解压 `phone_logs/mobile_log*.zip`（取第一个）
2. 再处理 `phone_logs/**/bugreports/bugreport*.zip` → `bugreport_main.txt`
3. 查找时优先 `bugreport_main.txt`，忽略 `dumpstate_log` 与本流程产物 txt

## 解析关键字

| 来源 | 关键字 | 说明 |
|------|--------|------|
| 时间轴 | `+longwake=` / `-longwake=` / `longwake=` | 持锁开始 / 释放 / 日志起点已持锁 |
| 时间轴 | `+wake_lock=` / `-wake_lock=` | partial wake lock（如 audioserver/1041） |
| 汇总 | `Wake lock u0a346 AudioMix: 56m 55s ...` | Battery Stats 累计 |
| UID→包名 | `com.xxx/u0a346`、`A=10346:com.xxx` | 自动映射持锁应用 |

时长分桶：**极长(≥30min)** / **长(5~30min)** / **中等(1~5min)** / **短(10s~1min)** / **极短(<10s)**。

## 输出

### DOU 摘要（高/低功耗根目录各一份）

| 文件 | 内容 |
|------|------|
| `bugreport_audiomix_result.json` | Top 持锁方、长持锁区间、详细产物路径；含 `"side": "high"|"low"` |
| `bugreport_audiomix_result.txt` | 人类可读结论摘要 |
| `bugreport_longwake_result.json` | 全部 longwake 摘要 |

### 详细时间轴（bugreport 目录）

| 文件 | 内容 |
|------|------|
| `bugreport_audiomix.txt` | 主视图：时间轴事件流 + 条带图 |
| `bugreport_audiomix.html` | 泳道图（浏览器打开） |
| `bugreport_audiomix.json` | 完整结构化数据 |
| `bugreport_longwake.{json,txt,html}` | 全部 longwake 详细产物 |

无 bugreport 时：摘要 JSON 写 `skipped: true`，退出码 0。

## 运行

### DOU 标准（推荐：显式 --low）

```powershell
chcp 65001 | Out-Null
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new()
$env:PYTHONUTF8 = "1"

$high = "<高功耗目录>"
$low  = "<低功耗目录>"
python analysis/domain/power/flow/dou_2/tool1_2/run_bugreport_audiomix.py $high --low $low
python analysis/domain/power/flow/dou_2/tool1_2/run_bugreport_longwake.py $high --low $low
```

未传 `--low` 时按顺序回退：`dou_prepare_result.json` → `scene_compare_result.json` → `power_analysis_result.json` 的 `low`；仍解析不到则只跑 high。

### 低层（直接指定 bugreport）

```powershell
python analysis/domain/power/flow/dou_2/bugreport_audiomix/run_bugreport_audiomix.py "<bugreport目录或txt>"
```

可选：`--low`、`--bugreport`、`--output-json`、`--output-txt`、`--output-html`。

## 目录结构

```
bugreport_audiomix/
├── SKILL.md
├── run_bugreport_audiomix.py          # 低层 CLI：AudioMix
├── run_bugreport_longwake.py          # 低层 CLI：全部 longwake
└── scripts/
    ├── parse_audiomix.py              # AudioMix 解析、bugreport 解压、场景对齐
    └── parse_longwake.py              # 全部 longwake 解析

tool1_2/run_bugreport_audiomix.py      # DOU 第 9 步（传 <high> [--low]）
tool1_2/run_bugreport_longwake.py      # DOU 第 9 步补充（传 <high> [--low]）
```

## Long Wakelock（全部 longwake）

AudioMix 是 `longwake=` 的一种 tag。全部 long wakelock 解析见 `scripts/parse_longwake.py`：

| 文件 | 路径 |
|------|------|
| 摘要 JSON | `<高/低功耗目录>/bugreport_longwake_result.json` |
| 详细 JSON/TXT/HTML | `<bugreport目录>/bugreport_longwake.{json,txt,html}` |

大类：**AudioMix（音频播放）** / 音频采集·通话 / 后台 Job / GMS 调度 / 媒体播放器 / 系统·其他。

## 说明

- 多应用同时持锁时，各 owner **分别统计**；按 owner 累加可能大于 Battery Stats 单 UID 汇总。
- `wake_lock` partial 若仅有 `-wake_lock` 无配对 `+`，区间可能为空，以 Battery Stats 汇总行为准。
- `1041` → `audioserver`，`1000` → `system`。
- **场景对齐**：从**同 side** 的 `<side>/meta_report/testReport.xlsx` 读取各场景 `starttime/endtime`，与持锁区间求重叠。
- **异常判定**（`scene_align.py`）：
  - **时长**：按场景类型（灭屏/待机/Feed/文档/相机/游戏等）设定 longwake 重叠阈值
  - **持锁方 × 场景**：判断该场景是否**应由该应用**持锁（不仅看是否音视频）
    - 例：相机/文档/下载场景出现 YouTube → 异常
    - 导航场景出现游戏/商店 → 异常
    - 游戏（MLBB 等）亮屏场景长时间 AudioMix → 异常
  - 通话/直播/TikTok/YouTube 等场景允许对应社交/播放应用

## 门禁

- DOU 全流程**必须执行**第 9 步命令（即使预期无 bugreport）。
- 存在 bugreport 时，建议同时跑 `run_bugreport_longwake.py` 与 `run_bugreport_audiomix.py`（high + low）。
- 存在 bugreport 时，各 side 的 `bugreport_audiomix_result.json` 的 `skipped` 不得为 true。

## HTML 报告展示

- Tab **「Long Wakelock」**：**高功耗 / 低功耗** 两个可折叠区块，**默认均收起**（标题行显示摘要：段数/异常数）
- 展开某一侧后：Long Wakelock 主页面 + AudioMix 副页面（子 Tab）
- 区块内细分泳道、汇总表、全部 AudioMix 区间亦**默认收起**
- 概览产物格：**Long Wakelock** / **AudioMix**；左侧徽章 **LongWake**
