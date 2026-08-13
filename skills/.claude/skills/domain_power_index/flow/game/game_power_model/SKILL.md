---
name: flow_power_game_power_model
description: 游戏功耗拆解模型：P_total 子系统划分、归因分类，以及从飞书加载硬件功耗台账（项目×版本×配置×机型）。
---
## 功能描述
flow 步骤 5。提供功耗分解公式、子系统责任域映射、问题五分类；并按 **项目 / 版本 / 配置 / 机型** 从飞书表格加载测试机与对比机的**硬件绝对功耗**，生成 `known_deltas` 供澄清报告「器件差异」使用。

## 飞书硬件功耗台账

推荐维护一张飞书**多维表格**（Wiki 内嵌 bitable 亦可；也兼容电子表格 sheets）：

当前默认数据源：
[硬件功耗台账（Wiki 多维表）](https://transsioner.feishu.cn/wiki/NWATwqEJiifoqRkcrygcLHKcnef?table=tbliLOHkosdbCdlQ&view=vewvz2zoGz)

| 项目 | 版本 | 配置 | 机型 | 屏_mA | 喇叭_mA | CPU_mA | RF_mA | 其它_mA | 备注 | 更新日期 |
|------|------|------|------|-------|---------|--------|-------|---------|------|----------|
| 项目1 | OS16.0.1 | basic | CN6 | 120 | 35 | 0 | 0 | 0 | 实验室 | 2026-07-01 |
| 项目1 | OS16.0.1 | basic | X6887 | 100 | 30 | 0 | 0 | 0 | 竞品 | 2026-07-01 |

配置填写：`hardware-power-source.yaml` 的 `source_url`（已填上述链接；`table`/`view` 从 URL 解析）。

运行时（已接入 `run_game_flow` 步骤 5）：
1. 每次跑 game：用测试机/对比机标签（如 CN6、X6878）从飞书拉表
2. **仅对比这两台**在飞书与本地 `hardware-power-by-project.json` 中的条目
3. 有差异 → **只更新这两台**相关 JSON 条目，其它机型缓存保留
4. 用最新数据生成 `known_deltas`（`delta = 测试机 - 对比机`）
5. 飞书失败则回退本地缓存，不阻断后续步骤

匹配：`--test-device` / `--compare-device` 对应表内「项目」列；可选 `--version` / `--config`（如一供）。

依赖：多维表需飞书应用**可读权限**。在文档中「添加文档应用 / 分享给应用」时，请按**应用名称**搜索（不要搜 `cli_xxx`）：

| 应用名称 | app_id |
|----------|--------|
| **软工 - 软件设计文档**（已用于本台账） | `cli_a8edf438c525100b` |
| 底软功耗自动化工具（可选，企业内可能搜不到） | `cli_a81049d61c2c900e` |

## 分析项
- **功耗公式**：`P_total = P_AP + P_Display + P_Audio + P_RF + P_Others`
- **子系统映射**：各域对应 flow 步骤 6~11
- **问题分类**：测试手法 / 硬件 / 策略 / 功能 / 异常
- **硬件台账**：`hardware_power.known_deltas`（屏/喇叭/CPU/RF/其它）

## 输入参数
| 参数 | 说明 |
|------|------|
| `--project` | 项目名（必填才会查台账） |
| `--version` / `--sw-version`（flow） | 软件版本 |
| `--config` / `--test-case` | 配置/场景（basic/nps） |
| `--test-device` / `--compare-device` | 机型标签（如 CN6 / X6887） |
| `--feishu-url` | 覆盖配置中的飞书 URL |
| `--offline-only` | 仅本地缓存 |
| `--analysis-dir` | 继承 `game_analysis_meta.json` 的 project/test_case |
| `--output` | 默认 `analysis/game_power_model.json` |

## 输出结果
`game_power_model.json`：
- `power_model`：公式与分类框架
- `hardware_power`：`status` / `source` / `sync` / `test` / `compare` / `known_deltas` / `missing`

步骤 14 诊断会自动把 `known_deltas` 灌入功耗差确认与器件差异表（CLI 显式 `--screen-delta-ma` 等优先）。

## 使用方法
```bash
# 配置飞书 URL
# 编辑 game_power_model/references/hardware-power-source.yaml → source_url

python .../game_power_model.py ^
  --output <analysis>/game_power_model.json ^
  --project 项目1 --version OS16.0.1 --config basic ^
  --test-device CN6 --compare-device X6887
```

## 注意事项
- 本步骤可不解析日志；硬件台账与日志分析正交
- 未配置飞书 URL 且本地缓存为空时，`hardware_power` 为 `empty`/`跳过`，不阻断后续步骤
- 同一项目多版本：尽量填准确 `version`；空版本时按机型+配置取最高匹配分
