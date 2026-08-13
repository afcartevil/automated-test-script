"""确认功耗差：问题单 I1、电流图结论、已知软硬件功耗差排除与分流。"""

from __future__ import annotations

from typing import Any


_KNOWN_DELTA_KEYS = (
    ("screen_delta_ma", "屏", "screen"),
    ("speaker_delta_ma", "喇叭", "speaker"),
    ("cpu_delta_ma", "CPU平台", "cpu"),
    ("rf_delta_ma", "WiFi/Modem", "rf"),
    ("other_hw_delta_ma", "其它硬件", "other_hw"),
    ("other_sw_delta_ma", "其它软件已知差", "other_sw"),
)


def _as_float(val: Any) -> float | None:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _collect_known_deltas(meta: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    nested = meta.get("known_deltas")
    if isinstance(nested, list):
        for row in nested:
            if not isinstance(row, dict):
                continue
            delta = _as_float(row.get("delta_ma") if "delta_ma" in row else row.get("value_ma"))
            module = str(row.get("module") or row.get("id") or "unknown")
            test_ma = _as_float(row.get("test_ma") or row.get("test_power_ma"))
            competitor_ma = _as_float(
                row.get("competitor_ma") or row.get("competitor_power_ma") or row.get("compare_ma")
            )
            if delta is None and test_ma is not None and competitor_ma is not None:
                delta = test_ma - competitor_ma
            if delta is None and test_ma is None and competitor_ma is None:
                continue
            items.append(
                {
                    "module": module,
                    "label": str(row.get("label") or row.get("module") or "已知差"),
                    "delta_ma": delta,
                    "test_ma": test_ma,
                    "competitor_ma": competitor_ma,
                    "note": str(row.get("note") or row.get("reason") or ""),
                    "optimization": str(
                        row.get("optimization") or row.get("optimization_plan") or row.get("fix") or ""
                    ),
                    "source": "known_deltas",
                }
            )
    for key, label, module in _KNOWN_DELTA_KEYS:
        delta = _as_float(meta.get(key))
        test_ma = _as_float(meta.get(f"{module}_test_ma") or meta.get(f"{key}_test"))
        competitor_ma = _as_float(
            meta.get(f"{module}_competitor_ma")
            or meta.get(f"{module}_compare_ma")
            or meta.get(f"{key}_competitor")
        )
        if delta is None and test_ma is None and competitor_ma is None:
            continue
        # avoid duplicate if already listed in known_deltas with same module
        if any(i.get("module") == module for i in items):
            continue
        if delta is None and test_ma is not None and competitor_ma is not None:
            delta = test_ma - competitor_ma
        items.append(
            {
                "module": module,
                "label": label,
                "delta_ma": delta,
                "test_ma": test_ma,
                "competitor_ma": competitor_ma,
                "note": str(
                    meta.get(f"{module}_note")
                    or meta.get(f"{key}_note")
                    or meta.get(f"{module}_reason")
                    or ""
                ),
                "optimization": str(
                    meta.get(f"{module}_optimization")
                    or meta.get(f"{key}_optimization")
                    or meta.get(f"{module}_fix")
                    or ""
                ),
                "source": "meta_flat",
            }
        )
    return items


def _waveform_section(meta: dict[str, Any]) -> dict[str, Any]:
    raw = meta.get("waveform_analysis")
    if not isinstance(raw, dict):
        raw = {}
    has_spike = raw.get("has_abnormal_spike")
    if has_spike is None:
        has_spike = meta.get("has_abnormal_current_spike")
    impact = raw.get("spike_impact_on_avg") or meta.get("spike_impact_on_avg") or ""
    avg_wo = _as_float(
        raw.get("avg_delta_without_spike_ma")
        if "avg_delta_without_spike_ma" in raw
        else meta.get("avg_delta_without_spike_ma")
    )
    conclusion = str(raw.get("conclusion") or meta.get("waveform_conclusion") or "").strip()
    if not conclusion:
        if has_spike is True:
            conclusion = (
                "问题单电流图存在异常抬高段；需评估对整体平均电流的影响，"
                "并对比去掉异常段后的平均电流差。"
            )
        elif has_spike is False:
            conclusion = "问题单电流图未标明异常抬高段；以整段平均电流差 I1 作为后续分析目标。"
        else:
            conclusion = (
                "未提供电流图结构化对比结论；请从问题单附图核对是否存在异常抬高电流段，"
                "并补充 spike / 去异常段后平均差。"
            )
    diff_points = raw.get("diff_points")
    if not isinstance(diff_points, list):
        diff_points = meta.get("current_diff_points") if isinstance(meta.get("current_diff_points"), list) else []
    dual = raw.get("dual_current_summary")
    if not isinstance(dual, dict):
        dual = meta.get("dual_current_summary") if isinstance(meta.get("dual_current_summary"), dict) else {}
    return {
        "has_abnormal_spike": has_spike,
        "spike_impact_on_avg": impact,
        "avg_delta_without_spike_ma": avg_wo,
        "avg_without_raised_windows_ma": _as_float(
            raw.get("avg_without_raised_windows_ma") or meta.get("avg_without_raised_windows_ma")
        ),
        "conclusion": conclusion,
        "coverage": "ok" if (has_spike is not None or conclusion or diff_points) else "missing",
        "source": raw.get("source") or "",
        "raised_window_count": raw.get("raised_window_count"),
        "diff_points": diff_points,
        "dual_current_summary": dual,
    }


def analyze_power_delta(report_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """确认功耗差并输出分流结论。

    I1 = 测试机功耗 - 竞品/对比机功耗（优先使用 delta_power_ma）。
    I  = 已知软硬件功耗差之和。
    分流：I >= I1 → known_delta_module；I < I1 → continue_analysis。
    """
    meta = dict(report_meta or {})
    test_ma = _as_float(meta.get("test_power_ma"))
    competitor_ma = _as_float(meta.get("competitor_power_ma"))
    i1 = _as_float(meta.get("delta_power_ma"))
    if i1 is None and test_ma is not None and competitor_ma is not None:
        i1 = test_ma - competitor_ma
    i1_source = str(meta.get("i1_source") or ("jira_meta" if i1 is not None else "")).strip()

    known_items = _collect_known_deltas(meta)
    known_sum = sum(float(x["delta_ma"]) for x in known_items if x.get("delta_ma") is not None) if known_items else 0.0
    known_sum_provided = any(x.get("delta_ma") is not None for x in known_items)

    adjusted_input = _as_float(meta.get("adjusted_delta_ma"))
    residual = None
    if i1 is not None:
        residual = i1 - (known_sum if known_sum_provided else 0.0)
        if adjusted_input is not None:
            # 允许外部直接给出「去除已知差后」的值，优先保留并交叉校验
            residual = adjusted_input

    route = "need_power_meta"
    route_reason = "缺少问题单功耗数据（test/competitor/delta），无法确认 I1。"
    if i1 is not None:
        src_note = ""
        if i1_source and i1_source != "jira_meta":
            src_note = f"（I1 来源：{i1_source}）"
        if known_sum_provided and known_sum >= i1:
            route = "known_delta_module"
            route_reason = (
                f"器件功耗合计 {known_sum:.1f} mA ≥ 差值 I1={i1:.1f} mA{src_note}，"
                "功耗差可由第 3 节器件拆解解释，无需继续异常排查。"
            )
        elif known_sum_provided and known_sum < i1:
            route = "continue_analysis"
            route_reason = (
                f"差异−器件功耗约 {max(i1 - known_sum, 0.0):.1f} mA"
                f"（I1={i1:.1f} − 器件合计 {known_sum:.1f}）{src_note}，"
                "继续做初步诊断与异常排查；器件分项见第 3 节。"
            )
        else:
            route = "continue_analysis"
            route_reason = (
                f"已确认 I1={i1:.1f} mA{src_note}，但器件功耗尚未量化；"
                f"暂按约 {i1:.1f} mA 继续分析，请补充第 3 节台账。"
            )

    waveform = _waveform_section(meta)
    unexplained = None
    if i1 is not None:
        unexplained = max(i1 - known_sum, 0.0) if known_sum_provided else i1

    return {
        "status": "ok" if i1 is not None else "partial",
        "jira_key": meta.get("jira_key") or "",
        "device_model": meta.get("device_model") or "",
        "test_power_ma": test_ma,
        "competitor_power_ma": competitor_ma,
        "delta_power_ma_i1": i1,
        "i1_source": i1_source or None,
        "known_deltas": known_items,
        "known_delta_sum_ma": known_sum if known_sum_provided else None,
        "residual_after_known_ma": residual if i1 is not None else None,
        "unexplained_ma": unexplained,
        "waveform_analysis": waveform,
        "routing": {
            "decision": route,
            "reason": route_reason,
            "rule": "I_known >= I1 → known_delta_module; I_known < I1 → continue_analysis",
        },
        "report_rows": {
            "test_power_ma": test_ma,
            "competitor_power_ma": competitor_ma,
            "i1_ma": i1,
            "known_sum_ma": known_sum if known_sum_provided else None,
            "after_known_ma": residual if i1 is not None else None,
        },
    }
