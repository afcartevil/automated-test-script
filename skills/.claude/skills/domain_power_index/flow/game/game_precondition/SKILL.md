---
name: flow_power_game_precondition
description: 游戏测试前置条件检查：对照 WBS 标准检测日志中测试环境是否合规。
---
## 功能描述
flow 步骤 4。对照 YAML 标准检查游戏测试前置条件（`flow/game/scripts` 内聚探测引擎）。须先完成步骤 2~3。

## 当前范围
读取并判定 **测试亮度 + 测试音量**（按项目×用例查表）。其它开关项暂缓。

标准来源（飞书）：[亮度和音量表](https://transsioner.feishu.cn/wiki/TTAVwmmIrif4uoknp1rcqRatn2V?sheet=4258R0)

| 测试用例 | 飞书列 | 日志来源 | 比对字段 |
|----------|--------|----------|----------|
| `basic` 基础场景 | 350nit / 72dB | `BrightnessCollector` / `TranAuraController` | `brightness_level` / `volume_index`（如项目1=140 / 13） |
| `nps` NPS场景 | 最大亮度 / 最大音量 | **sys** `DisplayPowerController` nits / 最大音量档 | `brightness_nits` / `volume_index` |

350nit / 72dB 是物理标定说明；基础场景比对等级与音量档，NPS 比对 nit 与最大音量档。

## 项目 / 场景解析（Agent）
1. **JIRA 日志**：传 `--jira-key`，从摘要/描述/`affect_project` 解析项目与 basic/nps
2. **路径日志**：TTY 下提示选择表中项目；或显式 `--project 项目1`
3. 结果写入 `analysis/game_analysis_meta.json`，供亮度/澄清报告复用

## 配置文件
| 文件 | 用途 |
|------|------|
| `references/brightness-volume-by-project.yaml` | 飞书表本地镜像 |
| `references/test-condition-standards.yaml` | `scope.enabled_items`、nit 容差 |

## 输入参数
1. **--project**：如 `项目1`
2. **--test-case**：`basic` / `nps`（也可用 `基础场景` / `最大亮度`）
3. **--jira-key**：可选，从单号解析项目/场景
4. **log_path** / **--window-json** / **--game-package**

## 使用方法
```bash
# 路径模式：指定项目
python .../game_precondition.py --project 项目1 --test-case basic

# JIRA 模式
python .../game_precondition.py --jira-key PROJ-12345

# NPS：DisplayPowerController nits 比对
python .../game_precondition.py --project 项目1 --test-case nps
```
