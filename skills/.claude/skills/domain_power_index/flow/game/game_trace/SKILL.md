---
name: flow_power_game_trace
description: 游戏场景 Perfetto/trace 解析（flow 步骤 8 子能力，CPU 频率分布与限频策略）。
---
## 功能描述
配合 [game_cpu_gpu_ddr](../game_cpu_gpu_ddr/SKILL.md) 步骤 3。

**推荐输入**：MTK PerformanceTools 从 trace 导出的 `perf-statistic.html`（Bokeh 内嵌 JSON），解析：

1. **CPU Loading**：cpu0..cpuN loading/idle
2. **频率分布**：`clusterN(cpuX) frequency histogram(MHz)` 各频点 residency%
3. **限频/提频策略启发式**：定频、抬底频、持续高频驻留
4. **Top 线程/进程**：By Thread / By Process loading
5. **线程大小核落核与 loading**：每线程 `little_cluster_pct` / `big_cluster_pct`（C0/C1）、`loading_on_little_pct` / `loading_on_big_pct`、Runnable、汇总 `thread_cluster_stats`
6. **CPU 动态功耗估算**（需 `--soc-model`）：loading × 簇频率驻留 × 能效表 OPP，输出大小核/合计 mW 与等效 mA@4V

原始 `.perfetto-trace` / `.ctrace` 的自动转换暂不内置；请先用 MTK 工具生成 HTML，再解析。

## 输入参数
1. **--perf-html**（推荐）：`perf-statistic.html` 路径
2. **--trace-path**（可选）：原始 trace；若同目录/`*-perfresult/` 下有 `perf-statistic.html` 会自动找到
3. **log_path**（可选）：默认在目录下搜索 `perf-statistic.html`
4. **--window-json**（可选）：仅写入关联元数据；**不要求**与 `T_game` 对齐（HTML 来自短时 trace，通常仅数秒）
5. **--soc-model**（可选但功耗估算必填）：机型代码（如 `CN6` / `LK7K`），查能效表「项目」sheet → 平台 OPP
6. **--xlsx**（可选）：能效表路径；默认 `references/energy_efficiency.xlsx`（同源 `aitools/energy_efficiency.xlsx`）
7. **--vdd**（可选）：电池侧等效电压，默认 `4.0`（`I_mA = P_mW / VDD`）

## 输出结果
`analysis/game_trace.json`：
- `cpu_loading`
- `cpu_frequency_distribution.clusters[]`（含 weighted_avg / peak / flags）
- `limit_policy`（fixed_freq / raised_floor / high_freq_clusters）
- `cpu_power`（`est_cpu_power_mW` / `little_cluster_mW` / `big_cluster_mW` / 每核明细；无 `--soc-model` 时 `status=skipped`）
- `threads[]` / `top_threads[]`（按 loading 排序，含大小核占比与 loading 拆分）
- `thread_cluster_stats`（落核分布计数、大/小核 loading 贡献 Top）
- `boost_attribution`（HTML 单独无法定责，confidence=low）
- `top_processes`
- `findings.summary`

功耗公式（与 `aitools/trace_compare` 一致，忽略 idle/漏电）：

```
P_i ≈ L_i × Σ_f P_act(cluster, f) × r_f
P_CPU = Σ_i P_i
I_mA = P_mW / VDD
```

## 使用方法
```bash
# 直接解析 MTK 导出的 HTML + 功耗估算
python analysis/domain/power/flow/game/game_trace/scripts/game_trace.py \
  --perf-html "D:/path/to/perf-statistic.html" \
  --soc-model CN6 \
  --output "<log_path>/analysis/game_trace.json"

# 或在 game_cpu_gpu_ddr 步骤 3 一并接入（需传 --soc-model）
python analysis/domain/power/flow/game/game_cpu_gpu_ddr/scripts/game_cpu_gpu_ddr.py \
  --perf-html "D:/path/to/perf-statistic.html" \
  --soc-model CN6
```

## 工作原理
1. 从 HTML 抽取 `<script type="application/json">` 的 Bokeh docs
2. 按 Figure title 识别 CPU Loading / cluster 频率直方图
3. 从 DataTable 提取 Top Thread / Process
4. 按 `references/analysis-standards.yaml` 阈值打 flags 并生成摘要
5. 若有 `--soc-model`：按 cluster 锚点切分核列表，用能效表就近匹配 OPP 估算动态功耗

## 注意事项
- HTML 来自 **短时 trace**（通常几秒）的聚合统计，**不必**与 `T_game` 对齐；代表采样窗口内的频率/负载分布，不是整局游戏平均
- HTML 无绝对时长时 `est_cpu_energy_mJ` 可能为 0（功率 mW/mA 仍可用）
- 跨机对比必须各自用自己机型的平台表（`--soc-model`），禁止混用
- 与步骤 6~11 的 `T_game` 证据交叉时，按「短窗采样」理解，勿当成全时段 residency
- `boost_attribution` 需与 main log 的 touch_boost / perfLockAcq 交叉（步骤 1）
- 部分样本可能缺某个 cluster 图，解析为 `coverage: partial` 仍可用
