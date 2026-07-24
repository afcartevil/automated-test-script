#!/usr/bin/env python3
import argparse
import html
import json
import re
from pathlib import Path


HTML_TEMPLATE = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Patch 分析报告</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 24px; color: #1f2937; }}
    h1, h2 {{ margin: 0 0 12px 0; }}
    .muted {{ color: #6b7280; }}
    .grid {{ display: grid; grid-template-columns: repeat(4, minmax(120px, 1fr)); gap: 12px; margin: 16px 0 20px 0; }}
    .card {{ border: 1px solid #e5e7eb; border-radius: 8px; padding: 12px; background: #fff; }}
    .v {{ font-size: 24px; font-weight: 700; margin-bottom: 6px; }}
    .k {{ font-size: 12px; color: #6b7280; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 12px; }}
    th, td {{ border: 1px solid #e5e7eb; padding: 8px; text-align: left; font-size: 13px; }}
    th {{ background: #f9fafb; position: sticky; top: 0; }}
    .ok {{ color: #0f766e; }}
    .warn {{ color: #a16207; }}
    .bad {{ color: #b91c1c; }}
    .pill {{ display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 12px; border: 1px solid #d1d5db; }}
    .tag {{ display: inline-block; padding: 2px 7px; border-radius: 999px; font-size: 12px; background: #eef2ff; color: #3730a3; border: 1px solid #c7d2fe; margin: 1px 3px 1px 0; }}
    .toolbar {{ display: flex; gap: 8px; margin: 8px 0 12px 0; }}
    input, select {{ padding: 6px 8px; border: 1px solid #d1d5db; border-radius: 6px; }}
    .detail-cell {{ background: #fcfcfd; }}
    details {{ cursor: pointer; }}
    details > summary {{ font-weight: 600; }}
    .detail-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 10px; }}
    .detail-card {{ border: 1px solid #e5e7eb; border-radius: 8px; padding: 10px; background: #fff; display: flex; flex-direction: column; height: 360px; overflow: hidden; }}
    .detail-title {{ font-size: 13px; font-weight: 600; margin-bottom: 6px; }}
    .detail-body {{ flex: 1; min-height: 0; overflow: auto; padding-right: 4px; }}
    .mini {{ font-size: 12px; color: #4b5563; line-height: 1.6; margin: 0; padding-left: 16px; }}
    .mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace; }}
    a {{ color: #2563eb; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    pre {{ margin: 8px 0 0 0; padding: 10px; border: 1px solid #e5e7eb; border-radius: 6px; background: #f9fafb; overflow: auto; font-size: 12px; line-height: 1.5; }}
    .report-block {{ border: 1px solid #e5e7eb; border-radius: 8px; padding: 10px; background: #fff; }}
    .report-block h4 {{ margin: 0 0 6px 0; font-size: 13px; }}
    .report-block p {{ margin: 0; font-size: 12px; color: #4b5563; line-height: 1.7; }}
    .logic-item {{ border-top: 1px solid #e5e7eb; padding-top: 10px; margin-top: 10px; }}
  </style>
</head>
<body>
  <h1>Patch 分析报告</h1>
  <p class="muted">仓库: {repo}<br/>区间: {from_tag} -> {to_tag}</p>

  <div class="grid">
    <div class="card"><div class="v">{total}</div><div class="k">区间总数</div></div>
    <div class="card"><div class="v">{analyzed}</div><div class="k">已分析</div></div>
    <div class="card"><div class="v">{avg_score}</div><div class="k">平均分</div></div>
    <div class="card"><div class="v">{blocked_count}</div><div class="k">阻断数</div></div>
  </div>

  <h2>建议分布</h2>
  <p class="muted">
    建议合入: {rec_ok} |
    有条件合入: {rec_cond} |
    需大幅修改: {rec_rework} |
    不建议合入: {rec_no}
  </p>
  <p class="muted">
    意图类标签（启发式，仅部分提交）: 「fix bug」{tag_fix_bug} 笔 | 「新需求」{tag_new_req} 笔
  </p>

  <div class="toolbar">
    <select id="recFilter">
      <option value="">全部建议</option>
      <option>建议合入</option>
      <option>有条件合入</option>
      <option>需大幅修改</option>
      <option>不建议合入</option>
    </select>
    <input id="kw" placeholder="按 commit/标题/风险过滤" />
  </div>

  <table id="t">
    <thead>
      <tr>
        <th>Commit</th>
        <th>标题</th>
        <th>分数</th>
        <th>建议</th>
        <th>阻断</th>
        <th>标签</th>
        <th>关键风险</th>
      </tr>
    </thead>
    <tbody>
      {rows}
    </tbody>
  </table>

  <script>
    const recFilter = document.getElementById('recFilter');
    const kw = document.getElementById('kw');
    const rows = Array.from(document.querySelectorAll('#t tbody tr.main-row'));
    function applyFilter() {{
      const rec = recFilter.value.trim();
      const q = kw.value.trim().toLowerCase();
      rows.forEach((r) => {{
        const rRec = (r.dataset.rec || '');
        const txt = (r.innerText || '').toLowerCase();
        const okRec = !rec || rRec === rec;
        const okKw = !q || txt.includes(q);
        const show = (okRec && okKw);
        r.style.display = show ? '' : 'none';
        const d = r.nextElementSibling;
        if (d && d.classList.contains('detail-row')) {{
          d.style.display = show ? '' : 'none';
        }}
      }});
    }}
    recFilter.addEventListener('change', applyFilter);
    kw.addEventListener('input', applyFilter);
  </script>
</body>
</html>
"""


def tone_class(rec: str, blocked: bool) -> str:
    if blocked or rec == "不建议合入":
        return "bad"
    if rec == "需大幅修改":
        return "warn"
    if rec == "建议合入":
        return "ok"
    return ""


def esc(v: object) -> str:
    return html.escape(str(v), quote=True)


def normalize_inline_text(text: object) -> str:
    return " ".join(str(text or "").split()).strip()


def shorten_text(text: str, limit: int) -> str:
    text = normalize_inline_text(text)
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def mostly_english(text: str) -> bool:
    ascii_letters = len(re.findall(r"[A-Za-z]", text))
    cjk_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    return ascii_letters >= 24 and cjk_chars <= 6


def split_sentences(text: str) -> list:
    parts = [x.strip() for x in re.split(r"(?<=[.!?])\s+", normalize_inline_text(text)) if x.strip()]
    return parts or ([normalize_inline_text(text)] if normalize_inline_text(text) else [])


def try_sample_based_problem_summary(paragraph: str) -> str:
    # Hook: later we can add real-sample rules here.
    # Expected usage:
    # - user provides a concrete commit sha / commit message sample
    # - add a targeted pattern and a high-quality Chinese summary
    # Keep this block ordered from most specific to least specific.
    _ = paragraph
    return ""


def summarize_issue_keywords(text: str) -> str:
    lowered = text.lower()
    labels = []
    mapping = [
        ("negative", "异常负值"),
        ("invalid", "非法输入/非法状态"),
        ("corrupt", "损坏数据"),
        ("warning", "告警"),
        ("crash", "崩溃"),
        ("fail", "失败"),
        ("deadlock", "死锁"),
        ("leak", "泄漏"),
        ("overflow", "溢出"),
        ("race", "竞争条件"),
    ]
    for key, label in mapping:
        if key in lowered and label not in labels:
            labels.append(label)
    return "、".join(labels[:3]) if labels else "异常场景"


def summarize_symbols(text: str) -> str:
    symbols = []
    for token in re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", text):
        if len(token) < 4:
            continue
        if token not in symbols:
            symbols.append(token)
        if len(symbols) >= 3:
            break
    return "、".join(symbols[:3]) if symbols else "相关路径"


def translate_effect_clause(clause: str) -> str:
    c = normalize_inline_text(clause).rstrip(".")
    lowered = c.lower()
    if "subsequent operation failures" in lowered or "subsequent operations fail" in lowered:
        return "后续操作失败"
    if "operation failures" in lowered:
        return "操作失败"
    if "crash" in lowered:
        return "崩溃"
    if "warning" in lowered:
        return "告警"
    if "invalid" in lowered:
        return "非法状态"
    if "deadlock" in lowered:
        return "死锁"
    if "leak" in lowered:
        return "资源泄漏"
    return "后续异常"


def translate_condition_clause(clause: str) -> str:
    c = normalize_inline_text(clause).rstrip(".")
    lowered = c.lower()
    if "opening this file" in lowered or "opening the file" in lowered:
        return "打开该文件时"
    if "open this file" in lowered or "open the file" in lowered:
        return "打开该文件时"
    if "reading" in lowered:
        return "读取相关数据时"
    if "parsing" in lowered:
        return "解析相关内容时"
    if "mount" in lowered:
        return "挂载相关对象时"
    return "相关路径中"


def pick_problem_paragraph_from_message(message: str) -> str:
    paragraphs = []
    current = []
    metadata_prefixes = ("Signed-off-by:", "Reviewed-by:", "Acked-by:", "Tested-by:", "Reported-by:", "Cc:", "Link:", "Bug:", "Closes:", "Fixes:")
    for raw in str(message or "").splitlines()[1:]:
        line = raw.strip()
        if not line:
            if current:
                paragraphs.append(" ".join(current))
                current = []
            continue
        if line.startswith(metadata_prefixes):
            continue
        current.append(line)
    if current:
        paragraphs.append(" ".join(current))
    for p in paragraphs:
        if re.search(r"(?i)\b(if|warning|warn|crash|broken|invalid|duplicate|syz|reproducer|fail|corrupt|deadlock|leak|overflow)\b", p):
            return normalize_inline_text(p)
    return normalize_inline_text(paragraphs[0]) if paragraphs else ""


def summarize_english_problem(paragraph: str) -> str:
    p = normalize_inline_text(paragraph)
    if not p:
        return ""

    sample_summary = try_sample_based_problem_summary(p)
    if sample_summary:
        return sample_summary

    translated_sentences = []
    for sentence in split_sentences(p):
        s = normalize_inline_text(sentence)
        if not s:
            continue
        m = re.search(r"(?i)^The reproducer builds? a corrupted file on disk with a negative ([A-Za-z0-9_]+) value\.?$", s)
        if m:
            field = m.group(1)
            translated_sentences.append(f"复现用例会在磁盘上构造一个 {field} 为负值的损坏文件。")
            continue

        m = re.search(r"(?i)^Add a check when opening (?:this|the) file to avoid (.+?)\.?$", s)
        if m:
            target = translate_effect_clause(m.group(1))
            translated_sentences.append(f"这笔修改在打开该文件时增加检查，以避免 {target}。")
            continue

        m = re.search(r"(?i)^Add a check (.+?) to avoid (.+?)\.?$", s)
        if m:
            when_clause = translate_condition_clause(m.group(1))
            target = translate_effect_clause(m.group(2))
            translated_sentences.append(f"这笔修改在 {when_clause} 增加检查，以避免 {target}。")
            continue

        m = re.search(r"(?i)^This happens when (.+?)\.?$", s)
        if m:
            translated_sentences.append("问题会在特定条件下触发。")
            continue

        m = re.search(r"(?i)^This can lead to (.+?)\.?$", s)
        if m:
            target = translate_effect_clause(m.group(1))
            translated_sentences.append(f"该问题会进一步导致 {target}。")
            continue

        m = re.search(r"(?i)^This causes? (.+?)\.?$", s)
        if m:
            target = translate_effect_clause(m.group(1))
            translated_sentences.append(f"该问题会导致 {target}。")
            continue

    if translated_sentences:
        return "正文指出：" + " ".join(translated_sentences)

    if mostly_english(p):
        issue_text = summarize_issue_keywords(p)
        symbol_text = summarize_symbols(p)
        return f"正文指出：该提交主要处理 {symbol_text} 上与 {issue_text} 相关的问题，并通过补充检查或防护避免后续失败。"
    return ""


def normalize_problem_context_for_display(data: dict, commit_message_full: str) -> str:
    context = normalize_inline_text(data.get("problem_context", "-")) or "-"
    if not mostly_english(context.replace("正文指出：", "")):
        return context
    fallback_paragraph = pick_problem_paragraph_from_message(commit_message_full)
    translated = summarize_english_problem(fallback_paragraph or context)
    return translated or context


def build_list_html(items: list) -> str:
    if not items:
        return "<p class='mini'>-</p>"
    return "<ul class='mini'>{}</ul>".format("".join("<li>{}</li>".format(esc(i)) for i in items))


TAG_RULES = [
    ("内存管理", ("mm/", "include/linux/mm", "include/linux/page", "include/linux/slab")),
    ("文件系统", ("fs/", "include/linux/fs", "include/linux/namei", "include/linux/dcache")),
    ("网络协议栈", ("net/", "include/net/", "drivers/net/")),
    ("驱动框架", ("drivers/",)),
    ("块设备/存储", ("block/", "include/linux/blk", "drivers/block/", "drivers/nvme/", "drivers/scsi/", "drivers/ufs/")),
    ("安全", ("security/", "include/linux/lsm", "include/linux/security", "certs/")),
    ("加密", ("crypto/", "include/crypto/")),
    ("调度", ("kernel/sched/", "include/linux/sched")),
    ("锁/并发", ("kernel/locking/", "include/linux/lock", "include/linux/rcu", "include/linux/atomic")),
    ("时间/定时器", ("kernel/time/", "include/linux/time", "drivers/clocksource/")),
    ("架构相关", ("arch/",)),
    ("虚拟化/KVM", ("virt/", "arch/x86/kvm/", "arch/arm64/kvm/", "include/linux/kvm", "include/uapi/linux/kvm")),
    ("BPF/eBPF", ("kernel/bpf/", "net/bpf", "include/linux/bpf", "tools/testing/selftests/bpf/")),
    ("IPC/进程通信", ("ipc/", "include/linux/ipc")),
    ("电源管理", ("kernel/power/", "drivers/cpufreq/", "drivers/cpuidle/", "drivers/power/", "include/linux/pm")),
    ("图形/DRM", ("drivers/gpu/drm/", "include/drm/")),
    ("多媒体", ("drivers/media/", "include/media/")),
    ("音频", ("sound/", "include/sound/")),
    ("USB", ("drivers/usb/", "include/linux/usb")),
    ("输入设备", ("drivers/input/", "include/linux/input")),
    ("Android/GKI", ("android/", "drivers/android/", "include/trace/hooks/", "kernel/trace/hooks/")),
    ("用户态接口", ("include/uapi/", "arch/x86/include/uapi/", "arch/arm64/include/uapi/")),
    ("测试", ("tools/testing/", "lib/kunit/", "kunit/", "samples/")),
    ("构建/Kconfig", ("Kconfig", "Makefile", "scripts/", "init/Kconfig")),
    ("文档", ("Documentation/",)),
]


PLATFORM_RULES = [
    ("ARM64", ("arch/arm64/", "include/uapi/asm-arm64/", "tools/arch/arm64/")),
    ("ARM", ("arch/arm/", "include/uapi/asm-arm/", "tools/arch/arm/")),
    ("x86", ("arch/x86/", "include/uapi/asm-x86/", "tools/arch/x86/")),
    ("RISC-V", ("arch/riscv/", "tools/arch/riscv/")),
    ("LoongArch", ("arch/loongarch/", "tools/arch/loongarch/")),
    ("MIPS", ("arch/mips/", "tools/arch/mips/")),
    ("PowerPC", ("arch/powerpc/", "tools/arch/powerpc/")),
    ("s390", ("arch/s390/", "tools/arch/s390/")),
    ("其他架构", ("arch/arc/", "arch/csky/", "arch/hexagon/", "arch/m68k/", "arch/microblaze/", "arch/nios2/", "arch/openrisc/", "arch/parisc/", "arch/sh/", "arch/sparc/", "arch/um/", "arch/xtensa/")),
]


def derive_tags_from_files(files: list) -> list:
    labels = []
    for label, prefixes in TAG_RULES:
        if any(any(path == prefix or str(path).replace("\\", "/").startswith(prefix) for prefix in prefixes) for path in files):
            if label not in labels:
                labels.append(label)
    return labels[:8] or ["通用内核"]


def derive_platforms_from_files(files: list) -> list:
    labels = []
    normalized_files = [str(path).replace("\\", "/") for path in files]
    for label, prefixes in PLATFORM_RULES:
        if any(any(path == prefix or path.startswith(prefix) for prefix in prefixes) for path in normalized_files):
            if label not in labels:
                labels.append(label)
    return labels[:6] or ["通用平台"]


def get_patch_tags(patch: dict) -> list:
    tags = patch.get("patch_tags") or []
    if tags:
        return tags
    files = [str(item.get("file", "")) for item in ((patch.get("code_change_analysis_rich") or {}).get("files_stat", []) or [])]
    return [{"label": label, "reason": "根据修改文件路径推断", "matched_files": []} for label in derive_tags_from_files(files)]


def get_platform_tags(patch: dict) -> list:
    tags = patch.get("platform_tags") or []
    if tags:
        return tags
    files = patch.get("files") or [
        str(item.get("file", "")) for item in ((patch.get("code_change_analysis_rich") or {}).get("files_stat", []) or [])
    ]
    return [{"label": label, "reason": "根据修改文件路径推断", "matched_files": []} for label in derive_platforms_from_files(files)]


def get_display_tags(patch: dict) -> list:
    merged = []
    seen = set()
    for tag in [*get_patch_tags(patch), *get_platform_tags(patch)]:
        label = str(tag.get("label", "")).strip()
        if not label or label in seen:
            continue
        seen.add(label)
        merged.append(tag)
    return merged or [{"label": "通用内核", "reason": "未命中明确标签规则", "matched_files": []}]


def build_tags_inline_html(tags: list) -> str:
    labels = [str(tag.get("label", "")).strip() for tag in tags if str(tag.get("label", "")).strip()]
    if not labels:
        labels = ["通用内核"]
    return "".join(f"<span class='tag'>{esc(label)}</span>" for label in labels[:6])


def build_tags_detail_html(tags: list) -> str:
    items = []
    for tag in tags:
        label = str(tag.get("label", "")).strip() or "通用内核"
        reason = str(tag.get("reason", "")).strip() or "根据修改文件路径推断"
        matched = tag.get("matched_files", []) or []
        matched_text = "；匹配文件：" + "、".join(str(x) for x in matched[:4]) if matched else ""
        items.append(f"{label}：{reason}{matched_text}")
    return build_list_html(items)


def build_score_details_html(score_details: dict, why_scored: list) -> str:
    lines = []
    intro = ""
    if why_scored:
        intro = (
            "<div class='mini' style='margin-bottom:8px'><span class='mono'>总体说明</span>:</div>"
            + "<ul class='mini'>"
            + "".join("<li>{}</li>".format(esc(item)) for item in why_scored)
            + "</ul>"
        )
    mapping = [
        ("correctness_completeness", "正确性与完整性"),
        ("risk_safety", "风险与安全性"),
        ("diff_maintainability", "Diff 可维护性"),
        ("commit_metadata_quality", "Commit/元信息质量"),
    ]
    for key, label in mapping:
        d = score_details.get(key, {})
        score = d.get("score", "-")
        weight = d.get("weight", "-")
        weighted = d.get("weighted_score", "-")
        reason = d.get("reason", "")
        breakdown = d.get("breakdown", {}) or {}
        base_score = breakdown.get("base_score", "-")
        additions = breakdown.get("additions", []) or []
        deductions = breakdown.get("deductions", []) or []
        final_raw_score = breakdown.get("final_raw_score", score)
        breakdown_parts = [
            "<div class='mini' style='margin-top:4px'><span class='mono'>基准分</span>: {}</div>".format(esc(base_score)),
            "<div class='mini' style='margin-top:4px'><span class='mono'>加分项</span>:</div>{}".format(build_list_html(additions)),
            "<div class='mini' style='margin-top:4px'><span class='mono'>减分项</span>:</div>{}".format(build_list_html(deductions)),
            "<div class='mini' style='margin-top:4px'><span class='mono'>最终原始分</span>: {}</div>".format(esc(final_raw_score)),
        ]
        lines.append(
            "<li><span class='mono'>{label}</span>: 分数 {score} / 权重 {weight} / 加权 {weighted}<br/>{reason}{breakdown}</li>".format(
                label=esc(label),
                score=esc(score),
                weight=esc(weight),
                weighted=esc(weighted),
                reason=esc(reason),
                breakdown="".join(breakdown_parts),
            )
        )
    return intro + "<ul class='mini'>{}</ul>".format("".join(lines))


def build_test_suggestions_html(suggestions: dict) -> str:
    rows = [
        ("单元测试", suggestions.get("unit_test", "-")),
        ("集成测试", suggestions.get("integration_test", "-")),
        ("回归测试", suggestions.get("regression_test", "-")),
        ("手工验证", suggestions.get("manual_validation", "-")),
        ("上线保障", suggestions.get("release_safeguard", "-")),
    ]
    return "<ul class='mini'>{}</ul>".format(
        "".join("<li><span class='mono'>{}</span>: {}</li>".format(esc(k), esc(v)) for k, v in rows)
    )


def build_commit_summary_variants(data: dict) -> dict:
    title = normalize_inline_text(data.get("title", "-")) or "-"
    context = normalize_inline_text(data.get("problem_context", "-")) or "-"
    constraint = normalize_inline_text(data.get("constraint_context", ""))
    original_summary = normalize_inline_text(data.get("summary", "-")) or "-"

    parts = [f"这笔提交的目标是“{title}”。"]
    if context and context != "-":
        parts.append(context)
    if constraint and constraint != "-":
        parts.append(constraint)

    full_summary = normalize_inline_text(" ".join(part for part in parts if part)) or original_summary
    return {
        "original": original_summary,
        "full": full_summary,
        "long": shorten_text(full_summary, 800),
    }


def build_closure_hint_text(fixes: list) -> str:
    if not fixes:
        return ""
    if any("syzkaller.appspot.com" in str(x) for x in fixes):
        return "该提交关联并关闭了一条 syzbot 缺陷报告。"
    return normalize_inline_text(fixes[0])


def build_commit_rich_html(data: dict, commit_message_full: str = "", summary_mode: str = "full") -> str:
    display_data = dict(data or {})
    display_data["problem_context"] = normalize_problem_context_for_display(display_data, commit_message_full)

    title = esc(display_data.get("title", "-"))
    context = esc(display_data.get("problem_context", "-"))
    constraint = esc(data.get("constraint_context", "-"))
    upstream_commit = esc(data.get("upstream_commit", ""))
    signals = data.get("signals", []) or []
    refs = data.get("references", []) or []
    fixes = data.get("fixes_closes", []) or []
    summary_variants = build_commit_summary_variants(display_data)
    closure_hint = esc(build_closure_hint_text(fixes))
    original_summary = esc(summary_variants["original"])
    long_summary = esc(summary_variants["long"])
    full_summary = esc(summary_variants["full"])

    if summary_mode == "full":
        summary_html = f"<p><span class='mono'>完整结论</span>: {full_summary}</p>"
    elif summary_mode == "long":
        summary_html = f"<p><span class='mono'>扩展结论</span>: {long_summary}</p>"
    elif summary_mode == "both":
        summary_html = (
            f"<p><span class='mono'>精炼结论</span>: {original_summary}</p>"
            f"<p><span class='mono'>完整结论</span>: {full_summary}</p>"
        )
    else:
        summary_html = f"<p><span class='mono'>精炼结论</span>: {original_summary}</p>"

    constraint_html = (
        f"<p><span class='mono'>约束/依据</span>: {constraint}</p>"
        if constraint and constraint != "-"
        else ""
    )
    upstream_html = (
        f"<p><span class='mono'>上游来源</span>: {upstream_commit}</p>" if upstream_commit else ""
    )
    closure_html = (
        f"<p><span class='mono'>闭环线索</span>: {closure_hint}</p>" if closure_hint else ""
    )
    return (
        "<div class='report-block'>"
        f"<p><span class='mono'>标题</span>: {title}</p>"
        f"<p><span class='mono'>背景</span>: {context}</p>"
        f"{constraint_html}"
        f"{upstream_html}"
        f"{summary_html}"
        f"{closure_html}"
        f"{build_list_html(['关键信号: ' + s for s in signals]) if signals else ''}"
        f"{build_list_html(['Fixes/Closes: ' + s for s in fixes]) if fixes else ''}"
        f"{build_list_html(['参考链接: ' + s for s in refs]) if refs else ''}"
        "</div>"
    )


def build_code_rich_html(data: dict) -> str:
    summary = esc(data.get("summary", "-"))
    files_stat = data.get("files_stat", []) or []
    logic_changes = data.get("logic_changes", []) or []
    stat_list = [f"{i.get('file','-')} (+{i.get('insertions',0)}/-{i.get('deletions',0)})" for i in files_stat[:6]]
    logic_html = []
    for item in logic_changes[:4]:
        location = esc(item.get("location", "-"))
        explanation = esc(item.get("explanation", "-"))
        before = esc(item.get("before", "")).strip()
        after = esc(item.get("after", "")).strip()
        block = [f"<div class='logic-item'><div class='mini'><span class='mono'>位置</span>: {location}</div>", f"<p>{explanation}</p>"]
        if before:
            block.append(f"<div class='mini'><span class='mono'>修改前</span></div><pre>{before}</pre>")
        if after:
            block.append(f"<div class='mini'><span class='mono'>修改后</span></div><pre>{after}</pre>")
        block.append("</div>")
        logic_html.append("".join(block))
    logic_section = (
        "".join(logic_html) if logic_html else "<p class='mini'>未提取到逻辑级代码变化解读。</p>"
    )
    return (
        "<div class='report-block'>"
        f"<p>{summary}</p>"
        f"{build_list_html(['主要文件: ' + x for x in stat_list]) if stat_list else ''}"
        f"{logic_section}"
        "</div>"
    )


def build_closure_rich_html(data: dict, problem_solved: str, change_summary: str) -> str:
    status = esc(data.get("status", "-"))
    confidence = esc(data.get("confidence", "-"))
    conclusion = esc(data.get("conclusion", "-"))
    why_fixed = esc(data.get("why_fixed", "-"))
    missing = esc(data.get("missing_evidence", "-"))
    acceptance = esc(data.get("acceptance", "-"))
    evidence = data.get("evidence", []) or []
    solved = esc(problem_solved or "-")
    return (
        "<div class='report-block'>"
        f"<p><span class='mono'>闭环状态</span>: {status}</p>"
        f"<p><span class='mono'>结论可信度</span>: {confidence}</p>"
        f"<p><span class='mono'>做了什么修改</span>: {esc(change_summary or '-')}</p>"
        f"<p><span class='mono'>问题归纳</span>: {solved}</p>"
        f"<p><span class='mono'>为什么说它解决了原问题</span>: {why_fixed}</p>"
        f"<p><span class='mono'>还缺什么证据</span>: {missing}</p>"
        f"<p><span class='mono'>是否建议直接接受这笔修复</span>: {acceptance}</p>"
        f"<p><span class='mono'>综合结论</span>: {conclusion}</p>"
        f"{build_list_html(['证据: ' + e for e in evidence]) if evidence else ''}"
        "</div>"
    )


def build_introducer_html(data: dict) -> str:
    detected = bool(data.get("detected", False))
    summary = esc(data.get("summary", "-"))
    confidence = esc(data.get("confidence", "-"))
    detection_method = esc(data.get("detection_method", "-"))
    introducer_commit = esc(data.get("introducer_commit", "-"))
    introducer_title = esc(data.get("introducer_title", "-"))
    commit_url = esc(data.get("introducer_commit_url", ""))
    diff_url = esc(data.get("introducer_diff_url", ""))
    change_summary = esc(data.get("introduced_change_summary", "-"))
    why = esc(data.get("why_introduced", "-"))
    evidence = data.get("evidence", []) or []
    links_html = ""
    if commit_url or diff_url:
        link_items = []
        if commit_url:
            link_items.append(f"<li><span class='mono'>引入提交</span>: <a href='{commit_url}' target='_blank'>{commit_url}</a></li>")
        if diff_url:
            link_items.append(f"<li><span class='mono'>引入 Diff</span>: <a href='{diff_url}' target='_blank'>{diff_url}</a></li>")
        links_html = "<ul class='mini'>{}</ul>".format("".join(link_items))
    introducer_html = (
        f"<p><span class='mono'>引入 patch</span>: {introducer_commit} - {introducer_title}</p>"
        if detected
        else ""
    )
    change_summary_html = (
        f"<p><span class='mono'>引入修改摘要</span>: {change_summary}</p>"
        if change_summary and change_summary != "-"
        else ""
    )
    why_html = (
        f"<p><span class='mono'>为什么认为它引入了问题</span>: {why}</p>"
        if why and why != "-"
        else ""
    )
    return (
        "<div class='report-block'>"
        f"<p><span class='mono'>是否识别到引入修改</span>: {'是' if detected else '否'}</p>"
        f"<p><span class='mono'>判断方式</span>: {detection_method}</p>"
        f"<p><span class='mono'>可信度</span>: {confidence}</p>"
        f"<p><span class='mono'>结论摘要</span>: {summary}</p>"
        f"{introducer_html}"
        f"{change_summary_html}"
        f"{why_html}"
        f"{links_html}"
        f"{build_list_html(['证据: ' + e for e in evidence]) if evidence else ''}"
        "</div>"
    )


def build_source_html(
    commit_url: str,
    diff_url: str,
    commit_message_full: str,
    diff_preview: dict,
) -> str:
    preview_text = esc((diff_preview or {}).get("text", ""))
    total_lines = (diff_preview or {}).get("total_lines", 0)
    preview_lines = (diff_preview or {}).get("preview_lines", 0)
    truncated = bool((diff_preview or {}).get("truncated", False))
    trunc_msg = "（已截断，点击原始 diff 查看完整内容）" if truncated else "（完整展示）"
    msg = esc(commit_message_full or "-")
    return (
        "<ul class='mini'>"
        "<li><span class='mono'>原始 commit 页面</span>: <a href='{commit_url}' target='_blank'>{commit_url}</a></li>"
        "<li><span class='mono'>原始 diff 页面</span>: <a href='{diff_url}' target='_blank'>{diff_url}</a></li>"
        "</ul>"
        "<details>"
        "<summary>展开查看 Commit Message 与 Diff 预览</summary>"
        "<div class='mini'><span class='mono'>Commit Message</span></div>"
        "<pre>{msg}</pre>"
        "<div class='mini'><span class='mono'>Diff 预览</span>: {preview_lines}/{total_lines} 行 {trunc_msg}</div>"
        "<pre>{preview}</pre>"
        "</details>"
    ).format(
        commit_url=esc(commit_url or "-"),
        diff_url=esc(diff_url or "-"),
        msg=msg,
        preview_lines=esc(preview_lines),
        total_lines=esc(total_lines),
        trunc_msg=esc(trunc_msg),
        preview=preview_text,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Render HTML report from patch analyzer JSON")
    parser.add_argument("--input", required=True, help="input JSON file")
    parser.add_argument("--output", default="patch-analysis-report.html", help="output HTML file")
    parser.add_argument(
        "--commit-summary-mode",
        choices=["original", "full", "long", "both"],
        default="full",
        help="how to render the commit interpretation summary",
    )
    args = parser.parse_args()

    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    summary = data.get("summary", {})
    rec_counts = summary.get("recommendation_counts", {})
    itc = summary.get("intent_tag_counts") or {}
    rows = []
    for p in data.get("patches", []):
        rec = str(p.get("recommendation", ""))
        blocked = bool(p.get("blocked", False))
        css = tone_class(rec, blocked)
        score_details = p.get("score_details", {})
        why_scored = p.get("why_scored", [])
        test_suggestions = p.get("test_suggestions", {})
        change_summary = p.get("change_summary", "")
        problem_solved = p.get("problem_solved", "")
        commit_interpretation_rich = p.get("commit_interpretation_rich", {})
        code_change_analysis_rich = p.get("code_change_analysis_rich", {})
        problem_closure_rich = p.get("problem_closure_rich", {})
        problem_introducer_rich = p.get("problem_introducer_rich", {})
        commit_url = p.get("commit_url", "")
        diff_url = p.get("diff_url", "")
        commit_message_full = p.get("commit_message_full", "")
        diff_preview = p.get("diff_preview", {})
        display_tags = get_display_tags(p)
        detail_html = (
            "<tr class='detail-row' data-rec='{rec}'>"
            "<td colspan='7' class='detail-cell'>"
            "<details>"
            "<summary>查看评分明细 / 建议测试项</summary>"
            "<div class='detail-grid'>"
            "<div class='detail-card'><div class='detail-title'>意图（Commit 信息）</div><div class='detail-body'>{commit_rich}</div></div>"
            "<div class='detail-card'><div class='detail-title'>代码变化（Code Diff）</div><div class='detail-body'>{code_rich}</div></div>"
            "<div class='detail-card' style='grid-column: span 2;'><div class='detail-title'>问题闭环（解决了什么）</div><div class='detail-body'>{closure_rich}</div></div>"
            "<div class='detail-card' style='grid-column: span 2;'><div class='detail-title'>问题引入（由哪笔引入）</div><div class='detail-body'>{introducer_rich}</div></div>"
            "<div class='detail-card' style='grid-column: span 2;'><div class='detail-title'>原始提交与 Diff</div><div class='detail-body'>{source}</div></div>"
            "<div class='detail-card'><div class='detail-title'>评分明细</div><div class='detail-body'>{score_details}</div></div>"
            "<div class='detail-card'><div class='detail-title'>建议测试项</div><div class='detail-body'>{test_suggestions}</div></div>"
            "</div>"
            "</details>"
            "</td>"
            "</tr>"
        ).format(
            rec=esc(rec),
            commit_rich=build_commit_rich_html(
                commit_interpretation_rich,
                commit_message_full=commit_message_full,
                summary_mode=args.commit_summary_mode,
            ),
            code_rich=build_code_rich_html(code_change_analysis_rich),
            closure_rich=build_closure_rich_html(problem_closure_rich, problem_solved, change_summary),
            introducer_rich=build_introducer_html(problem_introducer_rich),
            source=build_source_html(commit_url, diff_url, commit_message_full, diff_preview),
            score_details=build_score_details_html(score_details, why_scored),
            test_suggestions=build_test_suggestions_html(test_suggestions),
        )
        rows.append(
            "<tr class='main-row' data-rec='{rec}'>"
            "<td><code>{sha}</code></td>"
            "<td>{title}</td>"
            "<td>{score:.1f}</td>"
            "<td><span class='pill {css}'>{rec}</span></td>"
            "<td>{blocked}</td>"
            "<td>{tags}</td>"
            "<td>{risk}</td>"
            "</tr>{detail}".format(
                rec=rec,
                sha=esc(str(p.get("commit", ""))),
                title=esc(str(p.get("title", ""))),
                score=float(p.get("score", 0)),
                css=css,
                blocked="是" if blocked else "否",
                tags=build_tags_inline_html(display_tags),
                risk=esc(str(p.get("key_risk", ""))),
                detail=detail_html,
            )
        )

    html = HTML_TEMPLATE.format(
        repo=data.get("repo", "-"),
        from_tag=data.get("from_tag", "-"),
        to_tag=data.get("to_tag", "-"),
        total=data.get("total", 0),
        analyzed=data.get("analyzed", 0),
        avg_score=summary.get("avg_score", 0),
        blocked_count=summary.get("blocked_count", 0),
        rec_ok=rec_counts.get("建议合入", 0),
        rec_cond=rec_counts.get("有条件合入", 0),
        rec_rework=rec_counts.get("需大幅修改", 0),
        rec_no=rec_counts.get("不建议合入", 0),
        tag_fix_bug=itc.get("fix bug", 0),
        tag_new_req=itc.get("新需求", 0),
        rows="\n".join(rows),
    )
    Path(args.output).write_text(html, encoding="utf-8")
    print(f"HTML report generated: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
