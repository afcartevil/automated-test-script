"""基于汇总证据生成 AI 判断与补充建议（结构化，可再交 LLM 润色）。"""

from __future__ import annotations

from typing import Any


def _triggered(judgment: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in judgment.get("findings") or []:
        if isinstance(item, dict) and item.get("triggered"):
            out.append(item)
    if out:
        return out
    for item in judgment.get("primary_causes") or []:
        if isinstance(item, dict):
            out.append(item)
    return out


def _bucket_findings(triggered: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    buckets = {
        "test_methodology": [],
        "hardware_difference": [],
        "optimization_strategy": [],
        "feature_difference": [],
        "abnormal_situation": [],
        "other": [],
    }
    for item in triggered:
        cat = str(item.get("category_id") or item.get("category") or "other")
        if cat not in buckets:
            # map Chinese titles
            title = str(item.get("category_title") or "")
            mapping = {
                "测试手法": "test_methodology",
                "测试手法不符": "test_methodology",
                "器件差异": "hardware_difference",
                "不同优化策略": "optimization_strategy",
                "软件策略差异": "optimization_strategy",
                "功能差异": "feature_difference",
                "异常情况": "abnormal_situation",
                "异常问题": "abnormal_situation",
            }
            cat = mapping.get(title, "other")
        buckets.setdefault(cat, []).append(item)
    return buckets


def synthesize_ai_insights(
    *,
    power_delta: dict[str, Any],
    judgment: dict[str, Any],
    ctx: dict[str, Any] | None = None,
    external_ai: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """产出 AI 判断与建议。

    - 默认：基于规则命中 + 功耗差分流动态生成（可审计）
    - 若传入 external_ai（Agent/LLM 结果），合并进 findings/next_steps，并标记来源
    """
    ctx = ctx or {}
    triggered = _triggered(judgment)
    buckets = _bucket_findings(triggered)
    route = (power_delta.get("routing") or {}).get("decision")
    i1 = power_delta.get("delta_power_ma_i1")
    residual = power_delta.get("residual_after_known_ma")
    unexplained = power_delta.get("unexplained_ma")

    findings: list[dict[str, Any]] = []
    next_steps: list[str] = []
    human_review = False

    # 1) power delta narrative
    if route == "need_power_meta":
        findings.append(
            {
                "title": "功耗差尚未闭合",
                "severity": "high",
                "confidence": 0.9,
                "metrics": [],
                "evidence_ref": ["power_delta.routing"],
                "detail": "问题单测试机/竞品机电流或 I1 缺失，无法完成「确认功耗差」。",
            }
        )
        next_steps.append("从 JIRA 补充测试机/竞品机平均电流，或 CLI 传入 --test-power-ma/--competitor-power-ma/--delta-power-ma")
        human_review = True
    elif route == "known_delta_module":
        findings.append(
            {
                "title": "已知功耗差可覆盖 I1",
                "severity": "medium",
                "confidence": 0.85,
                "metrics": [
                    {"name": "I1_ma", "value": i1},
                    {"name": "known_sum_ma", "value": power_delta.get("known_delta_sum_ma")},
                ],
                "evidence_ref": ["power_delta.known_deltas"],
                "detail": (power_delta.get("routing") or {}).get("reason", ""),
            }
        )
        next_steps.append("转已知功耗差模块：核对屏/喇叭/CPU/RF 等器件与策略已知差台账是否与本次机型组合一致")
    else:
        findings.append(
            {
                "title": "已知差不足以解释 I1，需继续诊断",
                "severity": "high",
                "confidence": 0.8,
                "metrics": [
                    {"name": "I1_ma", "value": i1},
                    {"name": "unexplained_ma", "value": unexplained},
                    {"name": "residual_after_known_ma", "value": residual},
                ],
                "evidence_ref": ["power_delta.routing"],
                "detail": (power_delta.get("routing") or {}).get("reason", ""),
            }
        )

    wf = power_delta.get("waveform_analysis") or {}
    if wf.get("has_abnormal_spike") is True:
        findings.append(
            {
                "title": "电流图存在异常抬高段",
                "severity": "high",
                "confidence": 0.75,
                "metrics": [
                    {"name": "avg_delta_without_spike_ma", "value": wf.get("avg_delta_without_spike_ma")},
                ],
                "evidence_ref": ["power_delta.waveform_analysis"],
                "detail": wf.get("conclusion") or "",
            }
        )
        next_steps.append("在报告中标注异常电流段起止，并给出「去异常段后」平均电流差，避免被尖峰误导归因")
        human_review = True

    # 2) map primary diagnosis buckets to AI findings
    label_map = {
        "test_methodology": ("测试手法不符", "high"),
        "abnormal_situation": ("异常问题", "high"),
        "optimization_strategy": ("软件策略差异", "medium"),
        "feature_difference": ("功能差异需复核", "medium"),
        "hardware_difference": ("器件差异", "medium"),
    }
    for key, (title, sev) in label_map.items():
        items = buckets.get(key) or []
        if not items:
            continue
        labels = [str(x.get("label") or x.get("id") or "") for x in items[:6]]
        findings.append(
            {
                "title": title,
                "severity": sev,
                "confidence": 0.7 if key != "abnormal_situation" else 0.8,
                "metrics": [{"name": "hit_count", "value": len(items)}],
                "evidence_ref": [f"judgment.{key}"],
                "detail": "；".join(labels),
            }
        )

    # 3) contextual suggestions from key dimensions
    tw = ctx.get("game_time_window") or {}
    duration = None
    windows = tw.get("time_windows") or {}
    if isinstance(windows, dict):
        tg = windows.get("T_game") or {}
        duration = tg.get("duration_seconds")
    if duration is not None and float(duration) < 180:
        next_steps.append("游戏场景时长 <3min，建议复测拉长 T_game 后再对比平均电流")
        human_review = True

    thermal = ctx.get("game_thermal") or {}
    tsum = ((thermal.get("thermal_summary") or {}).get("during_game") or {})
    if tsum.get("freq_throttle") or tsum.get("thermal_backlight"):
        next_steps.append("存在 thermal 介入（限频/降背光）：优先判定为测试手法/温控策略，勿直接定软件异常")

    bg = ctx.get("game_background") or {}
    if (bg.get("category_breakdown_T_game") or {}).get("game_download"):
        next_steps.append("检测到后台下载，建议关闭下载/更新类任务后复测")

    net = ctx.get("game_network") or {}
    if (net.get("rf_stats") or {}).get("level") in ("weak", "suspect"):
        next_steps.append("网络信号弱/可疑：对照 WiFi<-90dBm / 数据弱场标准，排除发射功率抬升")

    # primary causes short summary
    primary = judgment.get("primary_causes") or []
    if primary:
        top = primary[0]
        summary = (
            f"初步主因倾向：[{top.get('priority')}] "
            f"{top.get('category_title') or ''} — {top.get('label') or top.get('subcategory') or ''}。"
        )
    else:
        summary = "规则引擎未给出强主因；需结合功耗差残留与人工复核电流图。"

    if route == "continue_analysis" and unexplained is not None:
        summary += f" 差异减去器件功耗后仍约有 {unexplained:.1f} mA 待解释。"

    # merge external AI (Agent/LLM)
    if isinstance(external_ai, dict) and external_ai:
        if external_ai.get("summary"):
            summary = str(external_ai.get("summary"))
        for f in external_ai.get("findings") or []:
            if isinstance(f, dict):
                f = dict(f)
                f.setdefault("source", "external_llm")
                findings.append(f)
        for s in external_ai.get("next_steps") or []:
            if s and str(s) not in next_steps:
                next_steps.append(str(s))
        if external_ai.get("human_review_required"):
            human_review = True

    # de-dup next_steps
    seen: set[str] = set()
    uniq_steps: list[str] = []
    for s in next_steps:
        if s not in seen:
            seen.add(s)
            uniq_steps.append(s)

    if not uniq_steps:
        uniq_steps.append("复核澄清报告中的 P0/P1 命中项，并补充竞品侧策略/器件对比数据")

    return {
        "status": "ok",
        "summary": summary,
        "findings": findings,
        "next_steps": uniq_steps,
        "human_review_required": human_review or bool(primary and str(primary[0].get("priority")) == "P0"),
        "category_hits": {k: len(v) for k, v in buckets.items() if v},
        "generator": "rule_synthesizer+optional_external_ai",
    }
