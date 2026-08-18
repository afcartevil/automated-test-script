#!/usr/bin/env python3
"""Generate combined CarrierConfig + SPN remote dashboard HTML (independent of carrierconfig package)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from spn_dashboard_cli import (
    default_combined_dashboard_html,
    load_combined_remote_datasets,
)


def render_combined_html(datasets: dict) -> str:
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    title = "Harness 远程数据看板（CarrierConfig + SPN）"
    hint = (
        "数据来源：Harness 统计服务后端（全团队远程数据）｜"
        "入口：<code>python spn_dashboard_cli.py remote --open</code> "
        "（与 CarrierConfig 同一界面，顶部 Tab 切换）"
    )
    cc = datasets["carrierconfig"]
    spn = datasets["spn"]
    payload = json.dumps(
        {
            "carrierconfig": {
                "records": cc["records"],
                "summary": cc["summary"],
                "fail_breakdown": cc["fail_breakdown"],
                "trend": cc["trend"],
                "generated_at": generated_at,
            },
            "spn": {
                "records": spn["records"],
                "summary": spn["summary"],
                "fail_breakdown": spn["fail_breakdown"],
                "platform_breakdown": spn["platform_breakdown"],
                "fault_link_breakdown": spn["fault_link_breakdown"],
                "trend": spn["trend"],
                "generated_at": generated_at,
            },
        },
        ensure_ascii=False,
    )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{title}</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
  <style>
    :root {{
      --bg: #0f1419; --card: #1a2332; --border: #2d3a4f; --text: #e8edf4;
      --muted: #8b9cb3; --pass: #22c55e; --fail: #ef4444; --warn: #f59e0b; --accent: #3b82f6;
      --spn: #a855f7;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      background: var(--bg); color: var(--text); min-height: 100vh; padding: 24px; }}
    h1 {{ font-size: 1.5rem; font-weight: 600; }}
    .header {{ display: flex; justify-content: space-between; align-items: center;
      margin-bottom: 16px; flex-wrap: wrap; gap: 12px; }}
    .meta {{ color: var(--muted); font-size: 0.85rem; }}
    .tabs {{ display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; }}
    .tab {{ background: var(--card); border: 1px solid var(--border); color: var(--muted);
      padding: 10px 18px; border-radius: 10px; cursor: pointer; font-size: 0.9rem; }}
    .tab.active {{ color: var(--text); border-color: var(--accent); box-shadow: inset 0 0 0 1px var(--accent); }}
    .tab[data-tab="spn"].active {{ border-color: var(--spn); box-shadow: inset 0 0 0 1px var(--spn); }}
    .panel {{ display: none; }}
    .panel.active {{ display: block; }}
    .kpi-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 16px; margin-bottom: 24px; }}
    .kpi {{ background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 20px; }}
    .kpi .label {{ color: var(--muted); font-size: 0.8rem; margin-bottom: 8px; }}
    .kpi .value {{ font-size: 2rem; font-weight: 700; }}
    .kpi.pass .value {{ color: var(--pass); }}
    .kpi.fail .value {{ color: var(--fail); }}
    .kpi.accent .value {{ color: var(--accent); }}
    .charts {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 16px; margin-bottom: 24px; }}
    .chart-card {{ background: var(--card); border: 1px solid var(--border);
      border-radius: 12px; padding: 20px; }}
    .chart-card h2 {{ font-size: 0.95rem; margin-bottom: 16px; color: var(--muted); }}
    .chart-wrap {{ position: relative; height: 260px; }}
    .table-card {{ background: var(--card); border: 1px solid var(--border);
      border-radius: 12px; padding: 20px; overflow-x: auto; }}
    .table-card h2 {{ font-size: 0.95rem; margin-bottom: 16px; color: var(--muted); }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
    th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid var(--border); }}
    th {{ color: var(--muted); font-weight: 500; }}
    .badge {{ display: inline-block; padding: 2px 8px; border-radius: 6px; font-size: 0.75rem; font-weight: 600; }}
    .badge.pass {{ background: rgba(34,197,94,0.15); color: var(--pass); }}
    .badge.fail {{ background: rgba(239,68,68,0.15); color: var(--fail); }}
    .badge.conditional {{ background: rgba(245,158,11,0.15); color: var(--warn); }}
    .empty {{ text-align: center; padding: 48px; color: var(--muted); }}
    .hint {{ background: var(--card); border: 1px dashed var(--border); border-radius: 12px;
      padding: 16px 20px; margin-bottom: 24px; color: var(--muted); font-size: 0.85rem; }}
    code {{ color: var(--accent); }}
  </style>
</head>
<body>
  <div class="header">
    <div>
      <h1>{title}</h1>
      <div class="meta" id="generatedAt"></div>
    </div>
  </div>
  <div class="tabs">
    <button class="tab active" data-tab="carrierconfig">CarrierConfig</button>
    <button class="tab" data-tab="spn">SPN</button>
  </div>
  <div class="hint">{hint}</div>

  <div id="panel-carrierconfig" class="panel active">
    <div class="kpi-grid" id="ccKpiGrid"></div>
    <div class="charts">
      <div class="chart-card"><h2>校验结果分布</h2><div class="chart-wrap"><canvas id="ccOutcomeChart"></canvas></div></div>
      <div class="chart-card"><h2>每日成功率趋势</h2><div class="chart-wrap"><canvas id="ccTrendChart"></canvas></div></div>
      <div class="chart-card"><h2>失败维度 Top</h2><div class="chart-wrap"><canvas id="ccFailChart"></canvas></div></div>
    </div>
    <div class="table-card"><h2>最近校验记录</h2><div id="ccTableWrap"></div></div>
  </div>

  <div id="panel-spn" class="panel">
    <div class="kpi-grid" id="spnKpiGrid"></div>
    <div class="charts">
      <div class="chart-card"><h2>分析结论分布</h2><div class="chart-wrap"><canvas id="spnOutcomeChart"></canvas></div></div>
      <div class="chart-card"><h2>每日分析通过率</h2><div class="chart-wrap"><canvas id="spnTrendChart"></canvas></div></div>
      <div class="chart-card"><h2>故障链路分布</h2><div class="chart-wrap"><canvas id="spnFaultChart"></canvas></div></div>
      <div class="chart-card"><h2>平台分布 (MTK/QCOM)</h2><div class="chart-wrap"><canvas id="spnPlatformChart"></canvas></div></div>
    </div>
    <div class="table-card"><h2>最近 SPN 分析记录</h2><div id="spnTableWrap"></div></div>
  </div>

  <script>
    const DATA = {payload};
    const charts = {{}};

    function badgeClass(pf) {{
      return pf === "PASS" ? "pass" : pf === "FAIL" ? "fail" : "conditional";
    }}

    function renderKpis(prefix, s, totalLabel) {{
      document.getElementById("generatedAt").textContent =
        "数据更新时间：" + DATA.carrierconfig.generated_at + " ｜ CarrierConfig " + DATA.carrierconfig.summary.total + " 条 ｜ SPN " + DATA.spn.summary.total + " 条";
      document.getElementById(prefix + "KpiGrid").innerHTML = `
        <div class="kpi pass"><div class="label">成功率 (PASS)</div><div class="value">${{s.success_rate}}%</div></div>
        <div class="kpi accent"><div class="label">平均准确率</div><div class="value">${{s.avg_accuracy}}%</div></div>
        <div class="kpi pass"><div class="label">通过</div><div class="value">${{s.pass_count}}</div></div>
        <div class="kpi fail"><div class="label">失败</div><div class="value">${{s.fail_count}}</div></div>
        <div class="kpi"><div class="label">条件通过</div><div class="value" style="color:var(--warn)">${{s.conditional_count}}</div></div>
        <div class="kpi"><div class="label">${{totalLabel}}</div><div class="value">${{s.total}}</div></div>`;
    }}

    function renderCcTable(records) {{
      const wrap = document.getElementById("ccTableWrap");
      if (!records.length) {{ wrap.innerHTML = '<div class="empty">暂无 CarrierConfig 校验记录</div>'; return; }}
      const rows = [...records].reverse().slice(0, 50).map(r => `
        <tr><td>${{r.jira_id}}</td><td>${{r.check_time}}</td>
        <td>${{r.accuracy_score != null ? r.accuracy_score + "%" : "-"}}</td>
        <td><span class="badge ${{badgeClass(r.pass_fail)}}">${{r.pass_fail}}</span></td>
        <td>${{r.platform || "-"}}</td><td>${{r.carrier_name || "-"}}</td>
        <td>${{r.fail_dimensions || "-"}}</td></tr>`).join("");
      wrap.innerHTML = `<table><thead><tr><th>Jira</th><th>校验时间</th><th>准确率</th><th>结论</th>
        <th>平台</th><th>运营商</th><th>失败维度</th></tr></thead><tbody>${{rows}}</tbody></table>`;
    }}

    function renderSpnTable(records) {{
      const wrap = document.getElementById("spnTableWrap");
      if (!records.length) {{
        wrap.innerHTML = '<div class="empty">暂无 SPN 远程记录。<br/>分析完成后通过 <code>spn/dashboard/record</code> 上传统计事件。</div>';
        return;
      }}
      const rows = [...records].reverse().slice(0, 50).map(r => `
        <tr><td>${{r.jira_id}}</td><td>${{r.check_time}}</td>
        <td>${{r.platform || "-"}}</td>
        <td><span class="badge ${{badgeClass(r.pass_fail)}}">${{r.pass_fail}}</span></td>
        <td>${{r.fault_link || "-"}}</td><td>${{r.operator_mccmnc || "-"}}</td>
        <td>${{r.workflow_state || "-"}}</td>
        <td>${{r.accuracy_score != null ? r.accuracy_score + "%" : "-"}}</td></tr>`).join("");
      wrap.innerHTML = `<table><thead><tr><th>Jira</th><th>分析时间</th><th>平台</th><th>结论</th>
        <th>故障链路</th><th>MCCMNC</th><th>工作流状态</th><th>准确率</th></tr></thead><tbody>${{rows}}</tbody></table>`;
    }}

    function chartOpts() {{
      return {{ responsive: true, maintainAspectRatio: false,
        plugins: {{ legend: {{ labels: {{ color: "#8b9cb3" }} }} }},
        scales: {{ x: {{ ticks: {{ color: "#8b9cb3" }}, grid: {{ color: "#2d3a4f" }} }},
          y: {{ ticks: {{ color: "#8b9cb3" }}, grid: {{ color: "#2d3a4f" }} }} }} }};
    }}

    function initOutcomeChart(id, summary, key) {{
      if (charts[key]) charts[key].destroy();
      charts[key] = new Chart(document.getElementById(id), {{ type: "doughnut",
        data: {{ labels: ["PASS","FAIL","CONDITIONAL"],
          datasets: [{{ data: [summary.pass_count, summary.fail_count, summary.conditional_count],
            backgroundColor: ["#22c55e","#ef4444","#f59e0b"], borderWidth: 0 }}] }},
        options: {{ responsive: true, maintainAspectRatio: false,
          plugins: {{ legend: {{ position: "bottom", labels: {{ color: "#8b9cb3" }} }} }} }} }});
    }}

    function initTrendChart(id, trend, key) {{
      const opts = chartOpts();
      if (charts[key]) charts[key].destroy();
      charts[key] = new Chart(document.getElementById(id), {{ type: "line",
        data: {{ labels: trend.dates.length ? trend.dates : ["暂无"],
          datasets: [{{ label: "成功率 %", data: trend.pass_rates.length ? trend.pass_rates : [0],
            borderColor: "#3b82f6", backgroundColor: "rgba(59,130,246,0.1)", fill: true, tension: 0.3 }}] }},
        options: {{ ...opts, scales: {{ ...opts.scales, y: {{ ...opts.scales.y, min: 0, max: 100 }} }} }} }});
    }}

    function initBarChart(id, breakdown, key, color) {{
      const opts = chartOpts();
      const labels = Object.keys(breakdown), values = Object.values(breakdown);
      if (charts[key]) charts[key].destroy();
      charts[key] = new Chart(document.getElementById(id), {{ type: "bar",
        data: {{ labels: labels.length ? labels : ["暂无"], datasets: [{{ label: "次数",
          data: values.length ? values : [0], backgroundColor: color }}] }}, options: opts }});
    }}

    function activateTab(name) {{
      document.querySelectorAll(".tab").forEach(el => el.classList.toggle("active", el.dataset.tab === name));
      document.querySelectorAll(".panel").forEach(el => el.classList.toggle("active", el.id === "panel-" + name));
    }}

    document.querySelectorAll(".tab").forEach(btn => {{
      btn.addEventListener("click", () => activateTab(btn.dataset.tab));
    }});

    renderKpis("cc", DATA.carrierconfig.summary, "总记录");
    renderKpis("spn", DATA.spn.summary, "总分析");
    renderCcTable(DATA.carrierconfig.records);
    renderSpnTable(DATA.spn.records);
    initOutcomeChart("ccOutcomeChart", DATA.carrierconfig.summary, "ccOutcome");
    initTrendChart("ccTrendChart", DATA.carrierconfig.trend, "ccTrend");
    initBarChart("ccFailChart", DATA.carrierconfig.fail_breakdown, "ccFail", "#ef4444");
    initOutcomeChart("spnOutcomeChart", DATA.spn.summary, "spnOutcome");
    initTrendChart("spnTrendChart", DATA.spn.trend, "spnTrend");
    initBarChart("spnFaultChart", DATA.spn.fault_link_breakdown, "spnFault", "#a855f7");
    initBarChart("spnPlatformChart", DATA.spn.platform_breakdown, "spnPlatform", "#3b82f6");
  </script>
</body>
</html>"""


def generate(*, output_path: Path | None = None, fetch_days: int = 365) -> tuple[Path, dict]:
    datasets = load_combined_remote_datasets(fetch_days=fetch_days)
    output = output_path or default_combined_dashboard_html()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_combined_html(datasets), encoding="utf-8")
    # 兼容旧打开路径：同步一份到 carrierconfig 目录
    legacy = Path.home() / ".tran_harness" / "carrierconfig" / "dashboard" / "remote_dashboard.html"
    try:
        legacy.parent.mkdir(parents=True, exist_ok=True)
        legacy.write_text(output.read_text(encoding="utf-8"), encoding="utf-8")
    except OSError:
        legacy = None
    return output, {"datasets": datasets, "legacy_html": str(legacy) if legacy else None}


if __name__ == "__main__":
    path, _meta = generate()
    print(path)
