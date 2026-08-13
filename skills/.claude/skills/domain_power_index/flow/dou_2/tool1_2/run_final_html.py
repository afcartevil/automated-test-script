from __future__ import annotations
def _setup_utf8_stdio() -> None:
    import sys
    for name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, name, None)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


import argparse
import html
import json
import os
import sys
import time
import webbrowser
from pathlib import Path


def _escape(s: object) -> str:
    return html.escape("" if s is None else str(s))


def _power_analysis_section_html(power_result: dict | None) -> str:
    # 兼容：允许直接传 analyze_high_power_scenario 的返回值（通常有 success/data）
    if not power_result:
        return ""
    if power_result.get("success") is not True:
        msg = power_result.get("message") or power_result.get("error") or "功耗分析未执行或失败"
        return f"""
        <div class="card border-warning mb-4 shadow-sm">
          <div class="card-header bg-warning text-dark">
            <h5 class="mb-0"><i class="fas fa-plug"></i> Modem / Wi-Fi 功耗对比</h5>
          </div>
          <div class="card-body small mb-0">{_escape(msg)}</div>
        </div>"""

    data = power_result.get("data") or {}
    comp = data.get("comparison") or {}
    v1 = data.get("version1") or {}
    v2 = data.get("version2") or {}
    vdp = data.get("valid_data_points") or {}

    metric_labels = {
        "on_power": "On 加权电流 (mA)",
        "off_power": "Off 加权电流 (mA)",
        "on_time": "On 时长 (h)",
        "off_time": "Off 时长 (h)",
    }

    rows_html: list[str] = []
    for comp_name, comp_zh in (("modem", "Modem"), ("wifi", "Wi-Fi")):
        sub = comp.get(comp_name) or {}
        for mk, label_zh in metric_labels.items():
            cell = sub.get(mk) or {}
            v1v = cell.get("version1")
            v2v = cell.get("version2")
            diff = cell.get("difference")
            dpct = cell.get("difference_percent")
            try:
                v1s = f"{float(v1v):.4f}" if v1v is not None else "--"
            except Exception:
                v1s = "--"
            try:
                v2s = f"{float(v2v):.4f}" if v2v is not None else "--"
            except Exception:
                v2s = "--"
            try:
                ds = f"{float(diff):+.4f}" if diff is not None else "--"
            except Exception:
                ds = "--"
            try:
                ps = f"{float(dpct):+.2f}%" if dpct is not None else "--"
            except Exception:
                ps = "--"
            badge = ""
            if cell.get("is_high_power"):
                badge = ' <span class="badge bg-danger">差异&gt;10%</span>'
            rows_html.append(
                f"<tr><td>{_escape(comp_zh)}</td><td>{_escape(label_zh)}</td>"
                f"<td class=\"text-end\">{_escape(v1s)}</td><td class=\"text-end\">{_escape(v2s)}</td>"
                f"<td class=\"text-end\">{_escape(ds)}</td><td class=\"text-end\">{_escape(ps)}{badge}</td></tr>"
            )

    # 新增：亮屏/灭屏综合加权功耗（mA）
    combined = comp.get("combined") or {}
    for mk, label_zh in (("on_power", "亮屏综合加权电流 (mA)"), ("off_power", "灭屏综合加权电流 (mA)")):
        cell = combined.get(mk) or {}
        v1v = cell.get("version1")
        v2v = cell.get("version2")
        diff = cell.get("difference")
        dpct = cell.get("difference_percent")
        try:
            v1s = f"{float(v1v):.4f}" if v1v is not None else "--"
        except Exception:
            v1s = "--"
        try:
            v2s = f"{float(v2v):.4f}" if v2v is not None else "--"
        except Exception:
            v2s = "--"
        try:
            ds = f"{float(diff):+.4f}" if diff is not None else "--"
        except Exception:
            ds = "--"
        try:
            ps = f"{float(dpct):+.2f}%" if dpct is not None else "--"
        except Exception:
            ps = "--"
        badge = ""
        if cell.get("is_high_power"):
            badge = ' <span class="badge bg-danger">差异&gt;10%</span>'
        rows_html.append(
            f"<tr><td>{_escape('综合')}</td><td>{_escape(label_zh)}</td>"
            f"<td class=\"text-end\">{_escape(v1s)}</td><td class=\"text-end\">{_escape(v2s)}</td>"
            f"<td class=\"text-end\">{_escape(ds)}</td><td class=\"text-end\">{_escape(ps)}{badge}</td></tr>"
        )

    wifi_row_v1 = v1.get("wifi_start_row", "")
    wifi_row_v2 = v2.get("wifi_start_row", "")
    extra = ""
    if wifi_row_v1 != "" or wifi_row_v2 != "":
        extra = (
            f"<p class=\"small text-muted mb-2\">Wi-Fi 分段起始行（Excel）：高功耗 {_escape(wifi_row_v1)} / "
            f"低功耗 {_escape(wifi_row_v2)}</p>"
        )

    n1 = vdp.get("version1", "")
    n2 = vdp.get("version2", "")
    valid_line = ""
    if n1 != "" or n2 != "":
        valid_line = f"<p class=\"small text-muted mb-0\">current 表有效数据点：高功耗 {_escape(n1)} / 低功耗 {_escape(n2)}</p>"

    table_body = "\n".join(rows_html) if rows_html else "<tr><td colspan=\"6\">无对比数据</td></tr>"

    return f"""
    <div class="card border-info mb-4 shadow-sm">
      <div class="card-header bg-info text-white">
        <h5 class="mb-0"><i class="fas fa-battery-three-quarters"></i> Modem / Wi-Fi 功耗对比（testReport current）</h5>
      </div>
      <div class="card-body">
        <p class="small mb-2">基于两目录下 <code>testReport.xlsx</code> 的 <code>report</code> / <code>current</code> 工作表；高功耗 vs 低功耗目录。</p>
        {extra}
        <div class="table-responsive">
          <table class="table table-sm table-bordered align-middle mb-2">
            <thead class="table-light">
              <tr>
                <th>组件</th>
                <th>指标</th>
                <th class="text-end">高功耗</th>
                <th class="text-end">低功耗</th>
                <th class="text-end">差值 (高−低)</th>
                <th class="text-end">差异比例</th>
              </tr>
            </thead>
            <tbody>
              {table_body}
            </tbody>
          </table>
        </div>
        {valid_line}
      </div>
    </div>"""


def _cpu_summary_html(cpu_data: dict) -> str:
    # 与旧 app.py 对齐：尝试给出均值摘要；失败则提示可展开 JSON
    try:
        averages_enhanced = cpu_data.get("averages_enhanced") or {}
        statistics = averages_enhanced.get("statistics") or {}
        if not statistics:
            return '<p class="small text-muted mb-0">已生成 CPU 分析数据（无增强统计时可展开原始 JSON）。</p>'

        scene1_avg = statistics.get("scene1_avg_cpu")
        scene2_avg = statistics.get("scene2_avg_cpu")
        total_unique = statistics.get("total_unique_processes") or 0

        def fmt(v: object) -> str:
            if v is None:
                return "--"
            try:
                return f"{float(v):.2f}"
            except Exception:
                return "--"

        a1 = fmt(scene1_avg)
        a2 = fmt(scene2_avg)
        return (
            f"<p class=\"small mb-0\"><strong>平均CPU</strong> 高功耗 {a1}% / 低功耗 {a2}% "
            f"&nbsp;|&nbsp; 唯一进程约 {total_unique} 个</p>"
        )
    except Exception:
        return '<p class="small text-muted mb-0">CPU 摘要生成失败。</p>'


def _ignored_scenes_section_html(ignored_scenes: list[dict]) -> str:
    if not ignored_scenes:
        return ""

    rows: list[str] = []
    for sc in ignored_scenes:
        desc = sc.get("desc", "") or ""
        name = sc.get("name", "") or ""
        suf = sc.get("suffix", "") or ""
        power_mah = sc.get("power_mah", "")
        on_ma = sc.get("impact_on_ma")
        off_ma = sc.get("impact_off_ma")
        reason = sc.get("ignore_reason") or sc.get("skip_reason") or "脚本问题"
        screen_label = sc.get("screen_label", "") or ""

        def _fmt_ma(v: object) -> str:
            if v is None or v == "":
                return "--"
            try:
                return f"{float(v):.4f}"
            except Exception:
                return "--"

        rows.append(
            f"<tr>"
            f"<td><strong>_{_escape(suf)}</strong><br><span class=\"text-muted small\">{_escape(desc)}</span>"
            f"<br><code class=\"small\">{_escape(name)}</code></td>"
            f"<td>{_escape(screen_label)}</td>"
            f"<td class=\"text-end\">{_escape(power_mah)}</td>"
            f"<td class=\"text-end\">{_escape(_fmt_ma(on_ma))}</td>"
            f"<td class=\"text-end\">{_escape(_fmt_ma(off_ma))}</td>"
            f"<td><span class=\"badge bg-secondary\">{_escape(reason)}</span></td>"
            f"</tr>"
        )

    table_body = "\n".join(rows)
    return f"""
        <div class="card border-secondary mb-4 shadow-sm">
          <div class="card-header bg-secondary text-white">
            <h5 class="mb-0"><i class="fas fa-ban"></i> 可忽略场景（脚本问题，未纳入 TopN 深度分析）</h5>
          </div>
          <div class="card-body">
            <p class="small text-muted mb-2">
              以下场景在 <code>ignorable_scenes.json</code> 中配置为可忽略：TopN 选取时已跳过，不执行 CPU/AI 分析。
              「对亮屏电流影响」「对灭屏电流影响」来自场景对比 Excel（mA）。
            </p>
            <div class="table-responsive">
              <table class="table table-sm table-bordered align-middle mb-0">
                <thead class="table-light">
                  <tr>
                    <th>场景</th>
                    <th>亮灭屏</th>
                    <th class="text-end">功耗差异 mAh</th>
                    <th class="text-end">对亮屏影响 (mA)</th>
                    <th class="text-end">对灭屏影响 (mA)</th>
                    <th>说明</th>
                  </tr>
                </thead>
                <tbody>
                  {table_body}
                </tbody>
              </table>
            </div>
          </div>
        </div>"""


def _build_html(
    top_scenes: list[dict],
    results: dict[str, dict],
    topn: int,
    summary_result: dict | None = None,
    power_result: dict | None = None,
    screen_filter_label: str = "",
    ignored_scenes: list[dict] | None = None,
) -> str:
    summary_html = ""
    if summary_result is not None:
        if summary_result.get("success") is True:
            smsg = summary_result.get("ai_reply") or summary_result.get("message") or ""
            summary_html = f"""
        <div class="card border-success mb-4 shadow-sm">
          <div class="card-header bg-success text-white">
            <h5 class="mb-0"><i class="fas fa-layer-group"></i> TopN 综合总结（AI）</h5>
          </div>
          <div class="card-body">
            <pre class="small bg-light p-3 rounded mb-0" style="white-space:pre-wrap;max-height:420px;overflow:auto;">{_escape(smsg)}</pre>
          </div>
        </div>"""
        else:
            warn = summary_result.get("message") or summary_result.get("error") or summary_result.get("ai_reply") or "综合总结未生成"
            summary_html = f"""
        <div class="card border-warning mb-4 shadow-sm">
          <div class="card-header bg-warning text-dark">
            <h5 class="mb-0"><i class="fas fa-exclamation-triangle"></i> TopN 综合总结</h5>
          </div>
          <div class="card-body small mb-0">{_escape(warn)}</div>
        </div>"""

    accordion_items: list[str] = []
    for i, sc in enumerate(top_scenes):
        suf = sc["suffix"]
        desc = sc.get("desc", "") or ""
        power_mah = sc.get("power_mah", 0)
        cpu_data = (results.get(suf) or {}).get("cpu_data") or {}
        ai_result = (results.get(suf) or {}).get("ai_result") or {}
        standby_result = (results.get(suf) or {}).get("standby_result") or {}

        cpu_html = _cpu_summary_html(cpu_data)

        if ai_result.get("success") is False:
            msg = ai_result.get("message") or ai_result.get("error") or "AI分析失败"
            ai_html = f'<div class="alert alert-warning small mb-0">{_escape(msg)}</div>'
        else:
            msg = ai_result.get("ai_reply") or ai_result.get("message") or ""
            ai_html = (
                "<pre class=\"small bg-light p-2 rounded\" style=\"white-space:pre-wrap;max-height:280px;overflow:auto;\">"
                f"{_escape(msg)}"
                "</pre>"
            )

        standby_html = ""
        if isinstance(standby_result, dict) and (
            standby_result.get("ai_reply")
            or standby_result.get("message")
            or results.get(suf, {}).get("is_long_standby")
        ):
            if standby_result.get("success") is False:
                smsg = (
                    standby_result.get("message")
                    or standby_result.get("error")
                    or "长待机分析失败"
                )
                standby_html = (
                    f'<div class="alert alert-warning small mb-0">{_escape(smsg)}</div>'
                )
            else:
                smsg = standby_result.get("ai_reply") or standby_result.get("message") or ""
                standby_html = (
                    "<pre class=\"small bg-light p-2 rounded\" style=\"white-space:pre-wrap;max-height:280px;overflow:auto;\">"
                    f"{_escape(smsg)}"
                    "</pre>"
                )

        heading_id = f"off-h-{i}"
        collapse_id = f"off-c-{i}"
        expanded = "show" if i == 0 else ""

        accordion_items.append(
            f"""
        <div class="accordion-item">
          <h2 class="accordion-header" id="{heading_id}">
            <button class="accordion-button {' ' if i == 0 else 'collapsed'}" type="button"
                    data-bs-toggle="collapse" data-bs-target="#{collapse_id}">
              <strong>_{_escape(suf)}</strong> &nbsp; {_escape(desc)} &nbsp;
              <span class="badge bg-secondary">{_escape(power_mah)} mAh</span>
            </button>
          </h2>
          <div id="{collapse_id}" class="accordion-collapse collapse {expanded}" data-bs-parent="#topn-off-acc">
            <div class="accordion-body">
              <h6 class="text-info">CPU 分析摘要</h6>
              {cpu_html}
              <h6 class="text-success mt-3">CPU 对比分析</h6>
              {ai_html}
              {"<h6 class=\"text-primary mt-3\">长待机分析（高功耗版）</h6>" + standby_html if standby_html else ""}
            </div>
          </div>
        </div>
""".strip()
        )

    items_html = "\n".join(accordion_items)
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    filter_badge = ""
    if (screen_filter_label or "").strip():
        filter_badge = f' <span class="badge bg-dark">筛选：{_escape(screen_filter_label)}</span>'

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>DOU TopN CPU+AI 最终结果（离线）</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
</head>
<body>
  <div class="container-fluid mt-4">
    <div class="card border-0 shadow-sm">
      <div class="card-header bg-primary text-white d-flex justify-content-between align-items-center flex-wrap gap-2">
        <h4 class="mb-0"><i class="fas fa-bolt"></i> TopN CPU + AI 最终结果（离线版）</h4>
        <div class="small text-white-50">生成时间：{_escape(ts)} | TopN={_escape(topn)}{filter_badge}</div>
      </div>
      <div class="card-body">
        <div class="alert alert-info">
          已按「功耗差异 mAh &gt; 0」取 TopN，逐个执行 CPU -&gt; AI 后，再进行 TopN 综合总结；并基于 power_analysis 结果展示 Modem/Wi-Fi 功耗对比。
        </div>
        {_power_analysis_section_html(power_result)}
        {summary_html}
        {_ignored_scenes_section_html(ignored_scenes or [])}
        <div id="topn-off-acc" class="accordion">
          {items_html if items_html else '<div class="alert alert-warning">没有可分析的 TopN 场景。</div>'}
        </div>
      </div>
    </div>
  </div>
  <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>"""


def main() -> int:
    _setup_utf8_stdio()
    parser = argparse.ArgumentParser(description="把拆分后的 JSON 渲染成最终 HTML（TopN CPU+AI）")
    parser.add_argument("top_scenes_json", help="run_topn_select.py 输出 top_scenes_json")
    parser.add_argument("results_json", help="run_collect_results.py 输出 results_json.json")
    parser.add_argument("power_analysis_json", help="run_power_analysis.py 输出 power_analysis_result.json")
    parser.add_argument("topn_summary_json", help="run_topn_summary.py 输出 topn_summary.json")
    parser.add_argument("--output", default="", help="输出 html 路径（默认同 high 目录）")
    parser.add_argument("--no-open", action="store_true", help="不自动打开浏览器")
    args = parser.parse_args()

    top_scenes_path = Path(args.top_scenes_json).resolve()
    results_path = Path(args.results_json).resolve()
    power_path = Path(args.power_analysis_json).resolve()
    summary_path = Path(args.topn_summary_json).resolve()

    for p in (top_scenes_path, results_path, power_path, summary_path):
        if not p.exists():
            print(f"文件不存在：{p}", file=sys.stderr)
            return 1

    this_dir = Path(__file__).resolve().parent
    scripts_dir = (this_dir / ".." / "scripts").resolve()
    sys.path.insert(0, str(scripts_dir))
    from utils import (  # noqa: E402
        clear_auto_error_ignorable_rules,
        parse_top_scenes_json,
        resolve_high_dir_from_artifact,
    )

    payload = json.loads(top_scenes_path.read_text(encoding="utf-8"))
    top_scenes, ignored_scenes, _ = parse_top_scenes_json(payload)
    results = json.loads(results_path.read_text(encoding="utf-8"))
    power_payload = json.loads(power_path.read_text(encoding="utf-8"))
    summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))

    # power_analysis_result.json 的结构：{"high","low","single_folder_mode","result":{...}}
    power_result = power_payload.get("result") if isinstance(power_payload, dict) else power_payload
    summary_result = summary_payload.get("summary") if isinstance(summary_payload, dict) else summary_payload

    topn = max(1, len(top_scenes) if isinstance(top_scenes, list) else 1)

    out_html_path = Path(args.output).resolve() if str(args.output).strip() else None
    if out_html_path is None:
        high = ""
        if isinstance(power_payload, dict):
            high = str(power_payload.get("high") or "")
        base_dir = Path(high) if high else results_path.parent
        stamp = time.strftime("%Y%m%d-%H%M%S")
        out_html_path = base_dir / f"topn_cpu_ai_results_{stamp}.html"

    html_str = _build_html(
        top_scenes=top_scenes,
        results=results,
        topn=topn,
        summary_result=summary_result,
        power_result=power_result,
        ignored_scenes=ignored_scenes,
    )
    out_html_path.parent.mkdir(parents=True, exist_ok=True)
    out_html_path.write_text(html_str, encoding="utf-8")
    print(f"已生成：{out_html_path}")

    high_dir = ""
    if isinstance(power_payload, dict):
        high_dir = str(power_payload.get("high") or "").strip()
    if not high_dir:
        high_dir = str(resolve_high_dir_from_artifact(results_path))
    removed = clear_auto_error_ignorable_rules(high_dir)
    if removed:
        print(f"已从 ignorable_scenes.json 清除本次 testReport error 临时规则：{removed} 条")

    if not bool(args.no_open):
        try:
            webbrowser.open(out_html_path.as_uri())
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

