"""DOU AI 分析：调用传音内部 OpenAI 兼容网关（默认 deepseek-v4-flash）。"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEFAULT_BASE_URL = "https://sw-aimodel.transsion-os.com/v1"
DEFAULT_MODEL = "deepseek-v4-flash"

# 兼容旧入口；新流程统一用 COMBINED_SCENE_SYSTEM_PROMPT（单次调用）。
SCENE_SYSTEM_PROMPT = """你是手机功耗与 CPU 性能分析工程师。用户会提供 DOU 单场景的 CPU 分析 JSON。
请严格按以下要求输出最终结论（只输出结论正文，不要复述输入）：

0）**已知问题优先**：先对照系统提示中的「已知问题库」。须同时满足条目量化门槛（如 KI-001 要求 CPU ≥ 约 70%）才算命中；命中则标注「已知问题」并按库内建议写，不要当新回归根因；仅进程名相似但未达门槛 → 不命中，按正常流程分析。
1）用中文写，大于500字,描述详细；但必须保留原文中的进程/线程/包名等拉丁标识（不要改写成“某应用/某进程”）每一段都需要具体分析功耗高的原因，不要只是列出进程。每一段记得换行。都要详细说明，是分析，不是直接列数据。
2）第1段：高功耗版本首先直接指出哪些进程异常**：分析这些进程是什么、为什么异常。)
3）第2段：重点分析高功耗版本新增的进程**（从无到有），这些可能是功耗增加的主要原因，减少的不用分析，具体分析。
4）第3段：对比高功耗高频进程**（出现10次以上或自身占比1/3以上的进程），不要对比binder进程，次数少与总出现次数1/3以上的进程不要对比，次数少于3次的不要对比
5）第4段：分析高功耗版本对比低功耗版本的CPU使用率增长变化大的进程**（增长超过10%）。
6）第5段：识别可能导致功耗差异的关键进程**，特别是高功耗版本中CPU使用率高的新进程。"""

CURRENT_SPIKE_SYSTEM_PROMPT = """你是手机功耗与电流曲线分析工程师。用户会提供 DOU 单场景的「电流图 + CPU 时段关联」JSON（含底电统计、差异最大时段、固定间隔差异分段 diff_segments、全场景 CPU 对比 cpu_scene_compare、分段内 CPU 进程对比）。
请严格按以下要求输出最终结论（只输出结论正文，不要复述输入）：

0）**已知问题优先**：先对照系统提示中的「已知问题库」。须同时满足条目量化门槛（如 KI-001 要求 CPU ≥ 约 70%）才算命中；命中则标注「已知问题」并按库内建议写，不要当新回归根因；仅进程名相似但未达门槛 → 不命中，按正常流程分析。
1）用中文写，大于400字，描述详细；保留原文中的进程/包名等拉丁标识（不要改写成“某应用/某进程”）。每一段换行，是分析而非罗列数据。
2）第1段：概述底电与均流差异——高/低版本底电(最低)、平均底电、对齐均差、Excel 均差等量化指标，判断整体电流偏高程度。
3）第2段：分析差异最大时段——结合 spike_windows 的相对时间、均差/峰值差，说明这些时段为何是功耗差异集中点。
4）第3段：分析 diff_segments 固定间隔分段——关注 mean_diff_ma 与 delta_from_prev_ma（差异扩大/缩小），找出电流差随时间恶化的关键区间；结合各段 cpu_in_segment.process_compare_top（本段相对上段的进程变化）说明哪些进程与分段电流变化对齐。
5）第4段：关联差异时段/分段内的 CPU——对比高/低版本 Top 进程与 Perf 块，并与 cpu_scene_compare（top_diff_processes、new_only_in_high/low、large_diff_processes）交叉验证。
6）第5段：给出根因推断与验证建议——哪些进程最可疑、建议抓什么日志或复现什么操作。"""

COMBINED_SCENE_SYSTEM_PROMPT = """你是手机功耗、电流曲线与 CPU 性能分析工程师。用户会一次提供同一 DOU 场景的两份 JSON：
A）cpu_analysis（全场景 CPU 对比摘要）
B）current_cpu_spike（电流图+CPU 时段关联：底电、spike_windows、diff_segments、cpu_scene_compare 等）

请**只做一次综合分析**，输出一份结论正文（不要复述输入，不要分两套独立报告标题重复铺垫）：

0）**已知问题优先**：先对照系统提示中的「已知问题库」。须同时满足条目量化门槛（如 KI-001 要求 CPU ≥ 约 70%）才算命中；进程/现象命中时，结论中明确标注「已知问题」，按库中判定与处理建议写，不要当作新的版本功耗回归根因深挖；仅进程名相似但未达门槛 → 不命中；未命中再按下列段落正常分析。
1）用中文写，大于700字，描述详细；保留进程/线程/包名等拉丁标识（禁止改写成“某应用/某进程”）。每段换行，是分析而非罗列数据。
2）第1段：底电与均流——结合 current_summary（底电最低、平均底电、对齐均差、Excel 均差）判断整体电流偏高程度。
3）第2段：电流差异时段——结合 spike_windows / diff_segments（mean_diff_ma、delta_from_prev_ma）说明差异何时集中、哪几段扩大/缩小。
4）第3段：高功耗异常/新增进程——结合 cpu_analysis 与 cpu_scene_compare，指出高功耗异常进程、从无到有的新增进程（减少的可不写），具体分析为何可疑。
5）第4段：高频与增长率——对比高频进程（出现≥10次或自身占比≥1/3；忽略 binder；次数<3 不比）及 CPU 增长率>10% 的进程。
6）第5段：时段↔进程对齐——用 spike/分段内 Top 进程与 process_compare_top，说明哪些进程与电流差时段对齐；与全场景对比交叉验证。
7）第6段：根因推断与验证建议——最可疑进程、建议抓什么日志或复现什么操作。"""

RECORD_FLAT_SECTION_HEADER = "【长按录制平缓段专项】"

RECORD_FLAT_SYSTEM_PROMPT = """你是手机功耗与 CPU 性能分析工程师。用户会提供 **Instagram 发布视频动态** 场景中「长按录制中间平缓段」的专项输入（与全场景综合 AI 无关）：
- 规则判定（划动/应用频繁、后台应用凸起、或底电分段）
- 平缓段时间窗内的高低电流差异统计
- 该时间窗内的 CPU Perf 块与 Top 进程（高/低版本）
- 可选：全场景五等分底电差异摘要

请**只针对长按录制平缓段**输出结论（不要复述输入，不要写全场景 TopN 总结）：

0）**已知问题优先**：对照系统提示中的「已知问题库」；须同时满足量化门槛才算命中。
1）中文 ≥350 字；保留进程/包名等拉丁标识；每段换行，是分析不是罗列。
2）第1段：复述规则判定含义——差异是否稳定、起伏次数/凸起时长、与底电五等分的关系。
3）第2段：结合平缓段 CPU——高/低版本 Top 进程、Perf 块对齐时间，判断是划动/渲染、应用频繁唤醒还是后台进程。
4）第3段：与全场景五等分底电对比——平缓段异常是否集中在某几份，是否支持底电/脚本/应用归因。
5）第4段：给出**本段专项**根因推断与验证建议（抓什么 log、复现什么操作）。"""

STANDBY_DOU_SYSTEM_PROMPT = """你是手机 DOU 长待机（flow_power_standby_long_dou）分析工程师。用户会提供同一灭屏长待机场景的结构化输入：
- testReport 场景时间段（sleep_time_start/end，用户指定窗，禁止改用 kernel 自动截取覆盖）
- pt5 拆机电流（stdby_curr_ma、高低功耗子窗；失败则整段降级、平均功耗 N/A）
- 可选 kernel standby 摘要（全窗 / 高功耗窗 / 低功耗窗）
- standby_type 与 threshold_ma（DOU 默认 WIFI/25mA）

请按 standby_long_dou 输出模板写**一份中文结论**（只输出正文，不要复述原始 JSON）：

0）**已知问题优先**：对照系统提示中的「已知问题库」；须同时满足量化门槛才算命中。
1）中文 ≥450 字；保留 Pending Wakeup / 进程包名 / R12 / lpm 模块等拉丁标识；每段换行。
2）第1段：问题描述——平台、待机模式（拆机 pt5）、时间段、平均功耗 vs 标准（25 或 30 mA）、pt5 是否降级。
3）第2段：电量/高低窗——最低/最高功耗窗时间与 mA；与 threshold 对照是否 Critical/Block。
4）第3段：系统休眠唤醒——AP suspend / 频繁唤醒 / 26M-LPM（MTK）或 Pending Wakeup Top3（高通）；责任模块。
5）第4段：CPU/应用——若有 CPU 异常 Top 进程则写清包名、PID、时段与负载；无则写 No。
6）第5段：根因推断与验证建议——唯一主因、机制、建议抓 log / 复现步骤、下一步 owner。

禁止调用 batteryinfo；禁止把 pt5 失败时的 N/A 电流写成实测值。"""

TOPN_SYSTEM_PROMPT = """你是手机功耗与 CPU 性能分析专家。用户会提供**某一亮灭屏分卷**（亮屏或灭屏）的 TopN 场景列表与每个场景的综合 AI 分析结果。
请基于本分卷全部场景输出「本分卷总结论」（只输出总结正文，不要复述输入，不要输出思考过程），要求：
0）**已知问题优先**：先对照系统提示中的「已知问题库」；须同时满足条目量化门槛（如 KI-001 要求 CPU ≥ 约 70%）才算命中；分卷内若多场景命中同一已知问题，合并说明并降级为「已知问题」优先级，不要当新回归反复强调；仅进程名相似但未达门槛 → 不命中。
1）开篇第一句写明本总结论所属分卷：【亮屏】或【灭屏】（与用户给出的 screen_label 一致）；只总结本分卷，不要把另一分卷场景混进来。
2）中文大于900 字，详细分析；必须保留进程/线程/包名等拉丁标识，禁止用“某应用/某进程”替代。
3）先写本分卷跨场景共性：结合电流时段与 CPU 综合结论具体分析。
4）【重点】按优先级列出本分卷最值得先验证/优化的点（可合并重复项），每点尽量附带量化信息（如电流差 mA、CPU 差异%、出现次数、功耗差异 mAh）。
5）结尾用一小段「本分卷总结论」收束：用 3～5 句给出本分卷根因优先级与验证顺序。"""


def _skill_root() -> Path:
    return Path(__file__).resolve().parent.parent


def load_known_issues() -> str:
    """读取 known_issues.md；供单场景 / TopN AI 总结前注入。"""
    path = _skill_root() / "known_issues.md"
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def system_prompt_with_known_issues(base_prompt: str) -> str:
    """在系统提示后追加已知问题库，保证每次 AI 总结前都能对照。"""
    issues = load_known_issues()
    if not issues:
        return base_prompt
    return (
        f"{base_prompt.rstrip()}\n\n"
        "===== 已知问题库（分析前必须先对照）=====\n"
        "若输入中的进程名/现象命中下列条目，且该条「特征 / 判定要点」中的量化门槛（如 CPU 占用率）"
        "在输入数据中已满足：结论须标注「已知问题」，按该条判定要点与处理建议书写，"
        "不要当作新的版本功耗回归根因。"
        "仅进程名相似但未达门槛 → 不得判定为已知问题，按正常流程分析。\n\n"
        f"{issues}"
    )


def load_ai_config() -> dict[str, Any]:
    """读取 ai_config.json（不含密钥）；环境变量优先。"""
    cfg_path = _skill_root() / "ai_config.json"
    cfg: dict[str, Any] = {}
    if cfg_path.is_file():
        try:
            raw = json.loads(cfg_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                cfg = raw
        except Exception:
            pass
    return cfg


def resolve_ai_settings(
    *,
    base_url: str = "",
    api_key: str = "",
    model: str = "",
) -> tuple[str, str, str]:
    cfg = load_ai_config()
    key = (
        api_key.strip()
        or os.environ.get("DOU_AI_API_KEY", "").strip()
        or os.environ.get("OPENAI_API_KEY", "").strip()
        or str(cfg.get("api_key") or "").strip()
    )
    if not key:
        raise RuntimeError(
            "未配置 API Key。请设置环境变量 DOU_AI_API_KEY。"
        )

    url = (
        base_url.strip()
        or os.environ.get("DOU_AI_BASE_URL", "").strip()
        or str(cfg.get("base_url") or DEFAULT_BASE_URL).strip()
    ).rstrip("/")
    if not url.endswith("/v1"):
        url = f"{url}/v1"

    mdl = (
        model.strip()
        or os.environ.get("DOU_AI_MODEL", "").strip()
        or str(cfg.get("model") or DEFAULT_MODEL).strip()
    )
    return url, key, mdl


def chat_completion(
    system_prompt: str,
    user_content: str,
    *,
    base_url: str = "",
    api_key: str = "",
    model: str = "",
    max_tokens: int = 8192,
    temperature: float = 0.3,
) -> str:
    from openai import OpenAI

    url, key, mdl = resolve_ai_settings(base_url=base_url, api_key=api_key, model=model)
    client = OpenAI(api_key=key, base_url=url)
    resp = client.chat.completions.create(
        model=mdl,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    msg = resp.choices[0].message
    content = (msg.content or "").strip()
    if not content:
        reasoning = getattr(msg, "reasoning_content", None) or ""
        content = str(reasoning).strip()
    if not content:
        raise RuntimeError("API 返回空内容")
    return content


def _unwrap_cpu_payload(cpu_payload: dict[str, Any]) -> dict[str, Any]:
    inner = cpu_payload.get("cpu_data")
    return inner if isinstance(inner, dict) else cpu_payload


def _slim_cpu_for_ai(cpu_payload: dict[str, Any]) -> dict[str, Any]:
    """Keep averages / stats for AI; drop heavy per-block process time series."""
    raw = _unwrap_cpu_payload(cpu_payload)
    slim: dict[str, Any] = {
        "suffix": cpu_payload.get("suffix") or raw.get("suffix"),
        "scene_desc": raw.get("scene_desc") or cpu_payload.get("scene_desc"),
        "averages_enhanced": raw.get("averages_enhanced"),
        "statistics": raw.get("statistics"),
    }
    for sk in ("scene1", "scene2"):
        s = raw.get(sk)
        if not isinstance(s, dict):
            continue
        slim[sk] = {
            "averages": s.get("averages"),
            "cpu_usage": s.get("cpu_usage") or s.get("cpu_usage_display"),
            "time_range": s.get("time_range"),
        }
    return slim


def analyze_scene_cpu_json(cpu_payload: dict[str, Any], **kwargs: Any) -> str:
    """兼容旧入口：仅 CPU。新流程请用 analyze_scene_combined_json。"""
    user_content = (
        "以下是 cpu_analysis JSON，请按系统提示要求输出分析结论：\n\n"
        + json.dumps(_slim_cpu_for_ai(cpu_payload), ensure_ascii=False, indent=2)
    )
    return chat_completion(
        system_prompt_with_known_issues(SCENE_SYSTEM_PROMPT), user_content, **kwargs
    )


def _slim_spike_for_ai(spike_payload: dict[str, Any]) -> dict[str, Any]:
    """Strip heavy chart series before current-spike AI API call."""
    slim: dict[str, Any] = {}
    for key in (
        "success",
        "suffix",
        "scene_desc",
        "scene_name",
        "scene_time",
        "current_summary",
        "spike_windows",
        "dip_windows",
        "segment_interval_sec",
        "diff_segments",
        "cpu_scene_compare",
        "perf_timeline",
        "cpu_source",
        "cpu_loaded",
        "time_axis_note",
        "analyzed_at",
    ):
        if key in spike_payload:
            slim[key] = spike_payload[key]
    series = spike_payload.get("series")
    if isinstance(series, dict):
        slim["series"] = {
            "sample_rate_hz": series.get("sample_rate_hz"),
            "point_count": series.get("point_count"),
        }
    timeline = slim.get("perf_timeline")
    if isinstance(timeline, dict):
        slim["perf_timeline"] = {
            "high": timeline.get("high") or [],
            "low": timeline.get("low") or [],
        }
    return slim


def analyze_current_spike_json(spike_payload: dict[str, Any], **kwargs: Any) -> str:
    """兼容旧入口：仅电流+CPU spike。新流程请用 analyze_scene_combined_json。"""
    slim = _slim_spike_for_ai(spike_payload)
    user_content = (
        "以下是 current_cpu_spike JSON（电流图+CPU 时段关联），请按系统提示要求输出分析结论：\n\n"
        + json.dumps(slim, ensure_ascii=False, indent=2)
    )
    return chat_completion(
        system_prompt_with_known_issues(CURRENT_SPIKE_SYSTEM_PROMPT), user_content, **kwargs
    )


def analyze_scene_combined_json(
    cpu_payload: dict[str, Any] | None,
    spike_payload: dict[str, Any],
    **kwargs: Any,
) -> str:
    """单场景唯一 AI 入口：CPU 对比 + 电流时段一次调用。"""
    slim_spike = _slim_spike_for_ai(spike_payload)
    slim_cpu = _slim_cpu_for_ai(cpu_payload) if isinstance(cpu_payload, dict) else None
    parts = [
        "以下是同一 DOU 场景的分析输入，请按系统提示做**一次综合分析**并输出结论：\n",
        "===== current_cpu_spike（电流图+CPU 时段）=====\n",
        json.dumps(slim_spike, ensure_ascii=False, indent=2),
    ]
    if slim_cpu:
        parts.extend(
            [
                "\n\n===== cpu_analysis（全场景 CPU 对比摘要）=====\n",
                json.dumps(slim_cpu, ensure_ascii=False, indent=2),
            ]
        )
    else:
        parts.append(
            "\n\n===== cpu_analysis =====\n（未提供独立 cpu_analysis；请主要依据 current_cpu_spike.cpu_scene_compare）"
        )
    call_kw = dict(kwargs)
    if not call_kw.get("max_tokens"):
        call_kw["max_tokens"] = 10240
    return chat_completion(
        system_prompt_with_known_issues(COMBINED_SCENE_SYSTEM_PROMPT),
        "".join(parts),
        **call_kw,
    )


def write_combined_ai_artifacts(
    *,
    results_dir: Path | str,
    suffix: str,
    ai_result: dict[str, Any],
    cpu_json: str = "",
    spike_json: str = "",
    power_mah: float = 0.0,
) -> tuple[Path, Path]:
    """一次 AI 结论同时落盘 ai_analysis_* 与 current_cpu_spike_ai_*（内容相同）。"""
    results = Path(results_dir)
    results.mkdir(parents=True, exist_ok=True)
    suf = str(suffix).strip().lstrip("_")
    success = bool(ai_result.get("success"))
    ai_path = results / f"ai_analysis_{suf}.json"
    spike_ai_path = results / f"current_cpu_spike_ai_{suf}.json"
    ai_payload = {
        "success": success,
        "suffix": suf,
        "cpu_json": cpu_json,
        "spike_json": spike_json,
        "power_difference_mAh": power_mah,
        "ai_mode": "combined",
        "ai_result": ai_result,
    }
    spike_ai_payload = {
        "success": success,
        "suffix": suf,
        "spike_json": spike_json,
        "cpu_json": cpu_json,
        "ai_mode": "combined",
        "ai_result": ai_result,
    }
    ai_path.write_text(json.dumps(ai_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    spike_ai_path.write_text(
        json.dumps(spike_ai_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return ai_path, spike_ai_path


def analyze_record_flat_json(payload: dict[str, Any], **kwargs: Any) -> str:
    """长按录制平缓段专项 AI（独立于全场景 combined AI）。"""
    call_kw = dict(kwargs)
    if not call_kw.get("max_tokens"):
        call_kw["max_tokens"] = 4096
    user_content = (
        "以下是「长按录制平缓段」专项分析输入，请按系统提示输出结论：\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )
    return chat_completion(
        system_prompt_with_known_issues(RECORD_FLAT_SYSTEM_PROMPT),
        user_content,
        **call_kw,
    )


def analyze_standby_dou_json(payload: dict[str, Any], **kwargs: Any) -> str:
    """DOU 长待机（standby_long_dou）专项 AI。"""
    call_kw = dict(kwargs)
    if not call_kw.get("max_tokens"):
        call_kw["max_tokens"] = 6144
    user_content = (
        "以下是 DOU 长待机（flow_power_standby_long_dou）分析输入，请按系统提示输出结论：\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )
    return chat_completion(
        system_prompt_with_known_issues(STANDBY_DOU_SYSTEM_PROMPT),
        user_content,
        **call_kw,
    )


def write_record_flat_ai_artifact(
    *,
    results_dir: Path | str,
    suffix: str,
    ai_result: dict[str, Any],
    context: dict[str, Any],
) -> Path:
    results = Path(results_dir)
    results.mkdir(parents=True, exist_ok=True)
    suf = str(suffix).strip().lstrip("_")
    out_path = results / f"record_flat_ai_{suf}.json"
    payload = {
        "success": bool(ai_result.get("success")),
        "suffix": suf,
        "ai_mode": "record_flat",
        "rule_id": context.get("rule_id") or "",
        "tag": context.get("tag") or "",
        "window": context.get("window") or {},
        "ai_result": ai_result,
        "context_summary": {
            k: context.get(k)
            for k in ("message", "stats", "quintiles", "cpu_in_window")
            if k in context
        },
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def compose_combined_ai_reply(
    combined_reply: str,
    record_flat_reply: str = "",
) -> str:
    """将平缓段专项 AI 追加到综合 AI 正文末尾（已存在则替换该段）。"""
    combined = str(combined_reply or "").strip()
    flat = str(record_flat_reply or "").strip()
    if not flat:
        return combined
    if RECORD_FLAT_SECTION_HEADER in combined:
        head = combined.split(RECORD_FLAT_SECTION_HEADER, 1)[0]
        combined = head.rstrip().removesuffix("---").strip()
    if not combined:
        return f"{RECORD_FLAT_SECTION_HEADER}\n\n{flat}"
    return f"{combined}\n\n---\n\n{RECORD_FLAT_SECTION_HEADER}\n\n{flat}"


def _read_record_flat_reply(results_dir: Path | str, suffix: str) -> tuple[str, bool | None]:
    results = Path(results_dir)
    suf = str(suffix).strip().lstrip("_")
    flat_path = results / f"record_flat_ai_{suf}.json"
    if not flat_path.is_file():
        return "", None
    try:
        payload = json.loads(flat_path.read_text(encoding="utf-8"))
        ai = payload.get("ai_result") or {}
        reply = str(ai.get("ai_reply") or ai.get("message") or "").strip()
        success = ai.get("success") if isinstance(ai, dict) else None
        return reply, success if isinstance(success, bool) else None
    except Exception:
        return "", None


def merge_record_flat_into_combined_artifacts(
    results_dir: Path | str,
    suffix: str,
    record_flat_reply: str = "",
    *,
    record_flat_success: bool | None = None,
) -> tuple[Path | None, Path | None]:
    """把 record_flat 专项结论写入 ai_analysis_* 与 current_cpu_spike_ai_* 的 ai_reply。"""
    flat = str(record_flat_reply or "").strip()
    if not flat:
        flat, auto_success = _read_record_flat_reply(results_dir, suffix)
        if record_flat_success is None:
            record_flat_success = auto_success
    if not flat:
        return None, None

    results = Path(results_dir)
    suf = str(suffix).strip().lstrip("_")
    ai_path = results / f"ai_analysis_{suf}.json"
    spike_ai_path = results / f"current_cpu_spike_ai_{suf}.json"
    updated: list[Path] = []
    for path in (ai_path, spike_ai_path):
        if not path.is_file():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        ai_result = payload.get("ai_result")
        if not isinstance(ai_result, dict):
            ai_result = {}
        combined = str(ai_result.get("ai_reply") or ai_result.get("message") or "")
        merged = compose_combined_ai_reply(combined, flat)
        ok = bool(ai_result.get("success", True))
        if record_flat_success is False:
            ok = False
        ai_result = {**ai_result, "success": ok, "ai_reply": merged}
        payload["ai_result"] = ai_result
        payload["record_flat_merged"] = True
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        updated.append(path)
    a_out = updated[0] if updated else None
    s_out = updated[1] if len(updated) > 1 else None
    return a_out, s_out


def _slim_results_for_summary(results_payload: dict[str, Any]) -> dict[str, Any]:
    """Strip heavy cpu_data before TopN summary API call (input length limit)."""
    slim: dict[str, Any] = {}
    for suffix, entry in results_payload.items():
        if not isinstance(entry, dict):
            slim[suffix] = entry
            continue
        ai = entry.get("ai_result") or {}
        slim[suffix] = {
            "power_difference_mAh": entry.get("power_difference_mAh"),
            "ai_result": {
                "success": ai.get("success"),
                "ai_reply": ai.get("ai_reply"),
            },
            "is_long_standby": entry.get("is_long_standby"),
            "standby_type": entry.get("standby_type"),
        }
        standby = entry.get("standby_result")
        if isinstance(standby, dict):
            slim[suffix]["standby_result"] = {
                "success": standby.get("success"),
                "ai_reply": standby.get("ai_reply"),
            }
    return slim


def summarize_topn(
    top_scenes_payload: Any,
    results_payload: dict[str, Any],
    *,
    screen_label: str = "",
    **kwargs: Any,
) -> str:
    slim_results = _slim_results_for_summary(results_payload)
    label = (screen_label or "").strip() or "未标注分卷"
    user_content = (
        f"本分卷 screen_label = 【{label}】。请只针对该分卷输出总结论（亮屏与灭屏必须分开，各有一份）。\n\n"
        "以下是本分卷 TopN 输入数据：\n\n"
        "===== top_scenes_json =====\n"
        + json.dumps(top_scenes_payload, ensure_ascii=False, indent=2)
        + "\n\n===== results_json =====\n"
        + json.dumps(slim_results, ensure_ascii=False, indent=2)
    )
    return chat_completion(
        system_prompt_with_known_issues(TOPN_SYSTEM_PROMPT),
        user_content,
        max_tokens=12288,
        **kwargs,
    )
