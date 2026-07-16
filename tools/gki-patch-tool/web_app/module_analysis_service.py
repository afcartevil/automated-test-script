"""模块级分析：按 dev_module 聚合 patch，生成代码树与 LLM 模块报告。"""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from web_app.dev_module_classifier import (
    get_dev_module_descriptions,
    group_patches_by_official_module,
    load_dev_modules,
    sort_modules_by_definition,
)
from web_app.analyzer_service import backfill_high_risk_patch_reason, patch_high_risk_reason
from web_app.database import get_task, get_task_patches, update_task
from web_app.repo_config import get_local_repo_dir


def _parse_patch_data(row: Dict[str, Any]) -> Dict[str, Any]:
    raw = row.get("data", "{}")
    try:
        data = json.loads(raw) if isinstance(raw, str) else dict(raw)
    except (json.JSONDecodeError, TypeError):
        data = {}
    data.setdefault("commit", row.get("sha", ""))
    data.setdefault("sha", row.get("sha", ""))
    data["dev_module"] = row.get("dev_module", "") or data.get("dev_module", "")
    data["score"] = row.get("score", data.get("score", 0))
    data["title"] = row.get("title", data.get("title", ""))
    return data


def group_patches_by_module(patches: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """按 dev_modules.txt 官方模块重新分类并分组。"""
    return group_patches_by_official_module(patches)


def build_module_stats(patches: List[Dict[str, Any]]) -> Dict[str, Any]:
    """模块级统计：patch 数、文件数、增删行、平均分、高风险数。"""
    files: set = set()
    insertions = 0
    deletions = 0
    scores: List[float] = []
    high_crash = 0
    blocked = 0
    for p in patches:
        for f in p.get("files", []) or []:
            if f:
                files.add(f)
        insertions += int(p.get("insertions", 0) or 0)
        deletions += int(p.get("deletions", 0) or 0)
        scores.append(float(p.get("score", 0) or 0))
        if p.get("blocked"):
            blocked += 1
        crash = (p.get("crash_risk") or "").strip()
        if crash in ("高", "中"):
            high_crash += 1
    return {
        "patch_count": len(patches),
        "files_changed": len(files),
        "insertions": insertions,
        "deletions": deletions,
        "avg_score": round(sum(scores) / len(scores), 1) if scores else 0.0,
        "blocked_count": blocked,
        "elevated_crash_count": high_crash,
    }


def _patch_brief(p: Dict[str, Any]) -> Dict[str, Any]:
    """代码树 UI 用的 patch 摘要（悬浮窗 / 展开详情）。"""
    sha = (p.get("commit") or p.get("sha", "") or "").strip()
    rich = p.get("commit_interpretation_rich") or {}
    summary = (rich.get("summary") or p.get("modification_interpretation") or "").strip()
    return {
        "sha": sha[:12],
        "full_sha": sha,
        "title": (p.get("title") or ""),
        "score": float(p.get("score", 0) or 0),
        "key_risk": (p.get("key_risk") or ""),
        "crash_risk": (p.get("crash_risk") or "").strip(),
        "llm_analyzed": bool(p.get("llm_analyzed")),
        "blocked": bool(p.get("blocked")),
        "summary": summary,
        "insertions": int(p.get("insertions", 0) or 0),
        "deletions": int(p.get("deletions", 0) or 0),
    }


def _dedupe_patch_briefs(briefs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: set = set()
    out: List[Dict[str, Any]] = []
    for b in briefs:
        key = b.get("full_sha") or b.get("sha")
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(b)
    out.sort(key=lambda x: float(x.get("score", 0) or 0))
    return out


def enrich_code_tree(code_tree: Dict[str, Any], patches: List[Dict[str, Any]]) -> Dict[str, Any]:
    """为代码树文件节点补充 path 与 patches（兼容旧 module_summaries）。"""
    by_full: Dict[str, List[Dict[str, Any]]] = {}
    by_leaf: Dict[str, List[tuple]] = {}
    for p in patches:
        brief = _patch_brief(p)
        for fp in p.get("files", []) or []:
            fp = fp.strip().lstrip("./")
            if not fp:
                continue
            by_full.setdefault(fp, []).append(brief)
            leaf = fp.rsplit("/", 1)[-1]
            by_leaf.setdefault(leaf, []).append((fp, brief))

    def _attach(node: Dict[str, Any]) -> None:
        if node.get("type") == "file" and node.get("name") != "…":
            if node.get("path") and node.get("patches"):
                return
            name = node.get("name", "")
            path = node.get("path", "")
            briefs: List[Dict[str, Any]] = []
            if path and path in by_full:
                briefs = list(by_full[path])
            elif name in by_leaf:
                matches = by_leaf[name]
                if len(matches) == 1:
                    path, briefs = matches[0][0], [matches[0][1]]
                else:
                    path = path or name
                    briefs = [m[1] for m in matches]
            if path:
                node["path"] = path
            if briefs:
                node["patches"] = _dedupe_patch_briefs(briefs)
        for child in node.get("children") or []:
            _attach(child)

    _attach(code_tree)
    return code_tree


def build_code_tree(patches: List[Dict[str, Any]]) -> Dict[str, Any]:
    """从 patch 变更文件构建完整目录树（不截断深度）。"""
    root: Dict[str, Any] = {"name": "/", "type": "dir", "patch_count": 0, "children": {}}

    def _ensure_child(parent: Dict[str, Any], name: str, is_file: bool) -> Dict[str, Any]:
        children = parent.setdefault("children", {})
        if name not in children:
            children[name] = {
                "name": name,
                "type": "file" if is_file else "dir",
                "patch_count": 0,
                "children": {} if not is_file else None,
            }
        return children[name]

    for p in patches:
        sha = (p.get("commit") or p.get("sha", "") or "").strip()
        brief = _patch_brief(p)
        for fp in p.get("files", []) or []:
            fp = fp.strip().lstrip("./")
            if not fp:
                continue
            parts = [x for x in fp.split("/") if x]
            if not parts:
                continue
            node = root
            node["patch_count"] = int(node.get("patch_count", 0)) + 1
            for i, part in enumerate(parts):
                is_file = i == len(parts) - 1
                node = _ensure_child(node, part, is_file)
                node["patch_count"] = int(node.get("patch_count", 0)) + 1
                if is_file:
                    node["path"] = fp
                    refs = node.setdefault("patch_refs", {})
                    if sha:
                        refs[sha] = brief

    return _tree_to_list(root)


def _tree_to_list(node: Dict[str, Any]) -> Dict[str, Any]:
    children = node.get("children") or {}
    sorted_children = sorted(
        children.values(),
        key=lambda c: (-int(c.get("patch_count", 0)), c.get("name", "")),
    )
    result = {
        "name": node.get("name", "/"),
        "type": node.get("type", "dir"),
        "patch_count": node.get("patch_count", 0),
    }
    if node.get("path"):
        result["path"] = node["path"]
    patch_refs = node.get("patch_refs")
    if patch_refs:
        result["patches"] = _dedupe_patch_briefs(list(patch_refs.values()))
    if sorted_children:
        result["children"] = [_tree_to_list(c) for c in sorted_children]
    return result


def format_code_tree_text(tree: Dict[str, Any], indent: int = 0) -> str:
    """将代码树格式化为缩进文本，供 LLM prompt 使用。"""
    lines: List[str] = []
    prefix = "  " * indent
    name = tree.get("name", "")
    count = tree.get("patch_count", 0)
    node_type = tree.get("type", "dir")
    marker = "📄" if node_type == "file" else "📁"
    if name != "/" or indent > 0:
        lines.append(f"{prefix}{marker} {name} ({count} patches)")
    for child in tree.get("children") or []:
        lines.extend(format_code_tree_text(child, indent + 1 if name != "/" else indent).splitlines())
    return "\n".join(lines)


def get_module_path_patterns(module_name: str) -> List[str]:
    patterns: List[str] = []
    for pat, name in load_dev_modules()["rules"]:
        if name == module_name:
            patterns.append(pat)
    return patterns


def get_module_diff_stat(
    from_tag: str,
    to_tag: str,
    module_name: str,
    repo_dir: Optional[Path] = None,
    max_chars: int = 12000,
) -> str:
    """获取模块相关路径的 git diff --stat（可选）。"""
    if not repo_dir or not from_tag or not to_tag:
        return ""
    patterns = get_module_path_patterns(module_name)
    if not patterns:
        return ""
    try:
        from tools.patch_analyzer import run_git
        pathspecs = patterns[:12]
        cmd = ["diff", "--stat", f"{from_tag}..{to_tag}", "--", *pathspecs]
        out = run_git(Path(repo_dir), cmd)
        if len(out) > max_chars:
            return out[:max_chars] + "\n... (stat truncated)"
        return out
    except Exception as exc:
        return f"(diff --stat 获取失败: {exc})"


def get_module_diff_content(
    from_tag: str,
    to_tag: str,
    module_name: str,
    repo_dir: Optional[Path] = None,
    max_chars: int = 0,
) -> str:
    """获取模块相关路径的合并 diff 内容，供 LLM 做代码级分析。"""
    if max_chars <= 0:
        from web_app.module_chunk_service import MODULE_DIFF_MAX_CHARS
        max_chars = MODULE_DIFF_MAX_CHARS
    if not repo_dir or not from_tag or not to_tag:
        return ""
    patterns = get_module_path_patterns(module_name)
    if not patterns:
        return ""
    try:
        from tools.patch_analyzer import run_git
        pathspecs = patterns[:12]
        cmd = ["diff", "-W", "-M", f"{from_tag}..{to_tag}", "--", *pathspecs]
        out = run_git(Path(repo_dir), cmd)
        if not out.strip():
            return ""
        if len(out) > max_chars:
            return out[:max_chars] + f"\n\n... (diff truncated, total {len(out)} chars) ..."
        return out
    except Exception as exc:
        return f"(模块 diff 获取失败: {exc})"


def _patch_digest_priority(p: Dict[str, Any]) -> tuple:
    from web_app.module_chunk_service import patch_priority_key
    return patch_priority_key(p)


def _build_patch_digest(
    patches: List[Dict[str, Any]],
    *,
    limit: int = 45,
    max_chars: int = 0,
) -> str:
    """构建模块 LLM 用的 patch 详细摘要（优先高风险与低分 patch）。"""
    if max_chars <= 0:
        from web_app.module_chunk_service import PATCH_DIGEST_MAX_CHARS
        max_chars = PATCH_DIGEST_MAX_CHARS
    if not patches:
        return "(无 patch)"

    ordered = sorted(patches, key=_patch_digest_priority)
    selected = ordered[:limit]
    lines: List[str] = [
        f"共 {len(patches)} 笔 patch，以下列出 {len(selected)} 笔（优先阻断/死机风险/低分）：",
        "",
    ]

    for p in selected:
        sha = (p.get("commit") or p.get("sha", ""))[:12]
        title = (p.get("title") or "")[:100]
        score = p.get("score", 0)
        rec = (p.get("recommendation") or "").strip()
        risk = (p.get("key_risk") or "").strip()
        blocked = p.get("blocked", False)
        crash = (p.get("crash_risk") or "").strip()
        crash_reason = (p.get("crash_risk_reason") or "").strip()

        files = [f.strip() for f in (p.get("files") or []) if f.strip()]
        files_preview = ", ".join(files[:6])
        if len(files) > 6:
            files_preview += f" …(+{len(files) - 6})"

        rich = p.get("commit_interpretation_rich") or {}
        if not isinstance(rich, dict):
            rich = {}
        interp = (rich.get("summary") or p.get("modification_interpretation") or "").strip()
        closure = (p.get("problem_solved") or "").strip()
        if not closure:
            closure_rich = p.get("problem_closure_rich") or {}
            if isinstance(closure_rich, dict):
                closure = (closure_rich.get("conclusion") or "").strip()
        intro = (p.get("introducer_analysis") or p.get("introduced_risk") or "").strip()

        # 单笔 rule_minimal：补提交说明，避免模块/总结 LLM 只看到类别套话
        if p.get("rule_based") or str(p.get("analysis_depth") or "") == "minimal":
            msg = str(
                p.get("commit_message_full")
                or p.get("commit_message")
                or ""
            ).strip()
            if msg:
                msg_one = re.sub(r"\s+", " ", msg)[:320]
                if msg_one and msg_one not in interp:
                    interp = f"{interp}\n提交说明: {msg_one}".strip() if interp else f"提交说明: {msg_one}"

        ts = p.get("test_suggestions", {}) or {}
        test_parts: List[str] = []
        if isinstance(ts, dict):
            for key, label in [
                ("unit_test", "单元"),
                ("integration_test", "集成"),
                ("regression_test", "回归"),
                ("manual_validation", "手工"),
                ("release_safeguard", "上线"),
            ]:
                val = (ts.get(key) or "").strip()
                if val:
                    test_parts.append(f"{label}: {val[:120]}")
        llm_test = (p.get("llm_test_suggestions") or "").strip()
        if llm_test:
            test_parts.append(f"LLM: {llm_test[:200]}")

        header = f"- `{sha}` [{score}] {title}"
        if blocked:
            header += " ⛔阻断"
        if rec:
            header += f" | 建议: {rec[:60]}"
        if risk:
            header += f" | 核心风险: {risk[:80]}"
        if crash:
            header += f" | 死机: {crash}"
        lines.append(header)
        if files_preview:
            lines.append(f"  文件: {files_preview}")
        if interp:
            lines.append(f"  修改解读: {interp[:220]}")
        if closure:
            lines.append(f"  问题闭环: {closure[:180]}")
        if intro:
            lines.append(f"  引入/新风险: {intro[:180]}")
        if crash_reason:
            lines.append(f"  死机原因: {crash_reason[:120]}")
        if test_parts:
            lines.append(f"  测试: {'；'.join(test_parts[:4])}")
        lines.append("")

    if len(patches) > limit:
        lines.append(f"... 另有 {len(patches) - limit} 笔 patch 未展开（已在统计与代码树中体现）")

    text = "\n".join(lines)
    if len(text) > max_chars:
        return text[:max_chars] + "\n... (digest truncated)"
    return text


def _build_module_risk_index(
    patches: List[Dict[str, Any]],
    *,
    max_chars: int = 12000,
) -> str:
    """模块内全量 patch 结构化索引，供 rollup 归纳（不依赖 raw diff）。"""
    if not patches:
        return "(无 patch)"
    lines: List[str] = [f"共 {len(patches)} 笔 patch，结构化索引（按风险优先）："]
    ordered = sorted(patches, key=_patch_digest_priority)
    for p in ordered:
        sha = (p.get("commit") or p.get("sha", ""))[:12]
        score = p.get("score", 0)
        title = (p.get("title") or "")[:60]
        risk = patch_high_risk_reason(p) or (p.get("key_risk") or "")[:50]
        flags: List[str] = []
        if p.get("blocked"):
            flags.append("阻断")
        crash = (p.get("crash_risk") or "").strip()
        if crash:
            flags.append(f"死机:{crash}")
        flag_str = f" [{','.join(flags)}]" if flags else ""
        risk_part = f" | {risk}" if risk else ""
        lines.append(f"- `{sha}` [{score}] {title}{flag_str}{risk_part}")
    text = "\n".join(lines)
    if len(text) > max_chars:
        return text[:max_chars] + "\n... (risk index truncated)"
    return text


def _module_diff_truncated(module_diff: str) -> bool:
    return bool(module_diff and "(diff truncated" in module_diff)


def _should_use_chunk_analysis(mod_patches: List[Dict[str, Any]], module_diff: str, llm: bool) -> bool:
    from web_app.module_chunk_service import SMALL_MODULE_THRESHOLD
    if not llm:
        return False
    if len(mod_patches) > SMALL_MODULE_THRESHOLD:
        return True
    return _module_diff_truncated(module_diff)


def _run_module_chunk_analysis(
    task: Dict[str, Any],
    module_name: str,
    mod_patches: List[Dict[str, Any]],
    *,
    from_tag: str,
    to_tag: str,
    repo_dir: Optional[Path],
    module_desc: str,
    stats: Dict[str, Any],
    code_tree: Dict[str, Any],
    diff_stat: str,
    cached_mod: Dict[str, Any],
    generate_module_chunk_summary,
    generate_module_rollup_summary,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any], Dict[str, Any]]:
    from web_app.module_chunk_service import (
        build_adaptive_module_chunks,
        build_coverage_metadata,
        build_high_risk_evidence,
        chunk_cache_key,
        get_chunk_diff_content,
        get_chunk_diff_stat,
        lookup_global_rollup,
        module_rollup_cache_key,
        patch_sha,
        resolve_chunk_cache_entry,
        store_global_rollup,
    )

    chunks = build_adaptive_module_chunks(
        mod_patches,
        from_tag=from_tag,
        to_tag=to_tag,
        repo_dir=repo_dir,
    )
    high_risk_evidence = build_high_risk_evidence(mod_patches, repo_dir)
    risk_index = _build_module_risk_index(mod_patches)
    chunk_summaries: List[Dict[str, Any]] = []
    chunk_cache_entries: Dict[str, Any] = {}
    task_id = str(task.get("id") or "")
    all_from_cache = True

    for chunk in chunks:
        cache_key = chunk_cache_key(module_name, chunk)
        cached = resolve_chunk_cache_entry(
            task_id,
            module_name,
            cache_key,
            task_mod_cache=cached_mod if isinstance(cached_mod, dict) else {},
        )
        if isinstance(cached, dict) and cached.get("summary"):
            chunk_summaries.append(cached["summary"])
            chunk_cache_entries[cache_key] = {
                "summary": cached["summary"],
                "cache_key": cache_key,
                "from_cache": True,
            }
            continue

        all_from_cache = False
        chunk_patches = chunk.get("patches") or []
        chunk_diff, truncated = get_chunk_diff_content(
            from_tag, to_tag, chunk_patches, repo_dir=repo_dir,
        )
        if chunk.get("split_exhausted"):
            truncated = True
        chunk_stat = get_chunk_diff_stat(
            from_tag, to_tag, chunk_patches, repo_dir=repo_dir,
        )
        chunk_tree = build_code_tree(chunk_patches)
        chunk_digest = _build_patch_digest(
            chunk_patches,
            limit=max(len(chunk_patches), 45),
        )
        chunk_high_risk = build_high_risk_evidence(chunk_patches, repo_dir)
        summary = generate_module_chunk_summary(
            task,
            module_name,
            chunk,
            chunk_tree,
            chunk_stat,
            chunk_digest,
            module_diff=chunk_diff,
            truncated_input=truncated,
            module_description=module_desc,
            high_risk_evidence=chunk_high_risk,
        )
        chunk_summaries.append(summary)
        chunk_cache_entries[cache_key] = {
            "summary": summary,
            "cache_key": cache_key,
        }

    rollup_key = module_rollup_cache_key(module_name, mod_patches)
    cached_rollup = lookup_global_rollup(module_name, rollup_key) if all_from_cache else None
    if isinstance(cached_rollup, dict) and cached_rollup.get("analysis"):
        analysis = cached_rollup["analysis"]
        print(f"[MODULE] rollup 命中全局缓存: {module_name}", flush=True)
    else:
        analysis = generate_module_rollup_summary(
            task,
            module_name,
            mod_patches,
            stats,
            code_tree,
            chunk_summaries,
            diff_stat=diff_stat,
            module_description=module_desc,
            high_risk_evidence=high_risk_evidence,
            risk_index=risk_index,
        )
        store_global_rollup(rollup_key, analysis, module_name=module_name)
    coverage = build_coverage_metadata(chunks, chunk_summaries, mod_patches)
    return analysis, chunk_summaries, chunks, coverage, chunk_cache_entries


def _script_module_analysis(
    module_name: str,
    patches: List[Dict[str, Any]],
    stats: Dict[str, Any],
    code_tree: Dict[str, Any],
) -> Dict[str, Any]:
    """无 LLM 时的规则化模块摘要。"""
    titles = [f"{(p.get('title') or '')[:60]}" for p in patches[:5]]
    return {
        "modification_interpretation": (
            f"模块「{module_name}」本区间共 {stats['patch_count']} 笔 patch，"
            f"涉及 {stats['files_changed']} 个文件，"
            f"+{stats['insertions']}/-{stats['deletions']} 行变更。"
            f"代表性变更：{'；'.join(titles)}"
        ),
        "code_changes": [
            {
                "location": child.get("name", ""),
                "explanation": f"{child.get('patch_count', 0)} 笔 patch 涉及",
            }
            for child in (code_tree.get("children") or [])[:8]
        ],
        "test_suggestions": f"针对 {module_name} 模块执行回归测试，覆盖上述 {stats['files_changed']} 个变更文件相关功能。",
        "crash_risk": "中" if stats.get("elevated_crash_count", 0) > 0 else "低",
        "crash_risk_reason": (
            f"有 {stats['elevated_crash_count']} 笔 patch 标记为中/高死机风险"
            if stats.get("elevated_crash_count", 0) > 0 else "未发现单笔高中死机风险标记"
        ),
        "high_risk_patches": [
            backfill_high_risk_patch_reason(
                patches,
                {
                    "sha": (p.get("commit") or p.get("sha", ""))[:12],
                    "title": (p.get("title") or "")[:60],
                    "reason": reason,
                    "risk": reason,
                    "score": p.get("score"),
                    "recommendation": p.get("recommendation"),
                    "blocked": p.get("blocked"),
                    "crash_risk": p.get("crash_risk"),
                    "key_risk": p.get("key_risk"),
                },
            )
            for p in sorted(patches, key=lambda x: float(x.get("score", 0) or 0))
            if (reason := patch_high_risk_reason(p))
        ][:8],
        "impact_scope": "",
        "problem_closure_summary": "",
        "verification_checklist": [],
        "cross_module_notes": "",
        "llm_generated": False,
    }


def _coverage_for_single_pass(
    mod_patches: List[Dict[str, Any]],
    module_diff: str,
) -> Dict[str, Any]:
    from web_app.module_chunk_service import patch_sha

    truncated = _module_diff_truncated(module_diff)
    return {
        "chunk_count": 1,
        "covered_patch_count": len(mod_patches),
        "total_patch_count": len(mod_patches),
        "truncated_chunk_count": 1 if truncated else 0,
        "split_exhausted_count": 0,
        "auto_split": False,
        "high_risk_patch_count": sum(1 for p in mod_patches if patch_high_risk_reason(p)),
        "patch_coverage_complete": True,
        "coverage_complete": not truncated,
    }


def run_module_analysis_for_task(
    task_id: str,
    progress_cb: Optional[Callable[[int, int, str], None]] = None,
    max_workers: Optional[int] = None,
) -> Dict[str, Any]:
    """对区间任务执行分模块分析，返回并持久化 module_summaries。

    始终使用完整模块/chunk/rollup LLM（或已缓存的同等完整结果）。
    单笔 patch 的 rule_minimal 免深析**不会**降低本阶段分析深度。
    """
    task = get_task(task_id)
    if not task:
        return {}
    if task.get("type") == "single":
        return {}

    rows = get_task_patches(task_id)
    if not rows:
        return {}

    patches = [_parse_patch_data(r) for r in rows]
    grouped = group_patches_by_module(patches)
    repo_dir = get_local_repo_dir()
    from_tag = task.get("from_tag", "")
    to_tag = task.get("to_tag", "")

    from web_app.llm_service import (
        generate_module_analysis,
        generate_module_chunk_summary,
        generate_module_rollup_summary,
        is_llm_configured,
    )
    from web_app.module_chunk_service import (
        apply_chunk_cache_batch,
        build_high_risk_evidence,
        load_chunk_cache,
        patch_sha,
    )

    results: Dict[str, Any] = {}
    modules = sort_modules_by_definition(list(grouped.items()))
    task_chunk_cache = load_chunk_cache(task_id)
    pending_chunk_cache: Dict[str, Dict[str, Any]] = {}

    from web_app.llm_service import resolve_module_worker_concurrency

    worker_count = (
        max_workers
        if max_workers is not None
        else resolve_module_worker_concurrency(len(modules))
    )
    print(
        f"[MODULE] 分模块分析并发 {worker_count} 路 / 共 {len(modules)} 个模块",
        flush=True,
    )

    def _analyze_one(item: Tuple[str, List[Dict[str, Any]]]) -> Tuple[str, Dict[str, Any]]:
        module_name, mod_patches = item
        stats = build_module_stats(mod_patches)
        code_tree = build_code_tree(mod_patches)
        diff_stat = get_module_diff_stat(from_tag, to_tag, module_name, repo_dir=repo_dir)
        module_diff = get_module_diff_content(from_tag, to_tag, module_name, repo_dir=repo_dir)
        digest = _build_patch_digest(mod_patches)
        module_desc = get_dev_module_descriptions().get(module_name, "")
        chunk_summaries: List[Dict[str, Any]] = []
        chunk_cache_entries: Dict[str, Any] = {}
        coverage: Dict[str, Any]
        cached_mod = task_chunk_cache.get(module_name) or {}
        llm_on = is_llm_configured()
        use_chunks = _should_use_chunk_analysis(mod_patches, module_diff, llm_on)

        if use_chunks:
            analysis, chunk_summaries, _chunks, coverage, chunk_cache_entries = (
                _run_module_chunk_analysis(
                    task,
                    module_name,
                    mod_patches,
                    from_tag=from_tag,
                    to_tag=to_tag,
                    repo_dir=repo_dir,
                    module_desc=module_desc,
                    stats=stats,
                    code_tree=code_tree,
                    diff_stat=diff_stat,
                    cached_mod=cached_mod if isinstance(cached_mod, dict) else {},
                    generate_module_chunk_summary=generate_module_chunk_summary,
                    generate_module_rollup_summary=generate_module_rollup_summary,
                )
            )
        elif llm_on:
            from web_app.module_chunk_service import (
                lookup_global_rollup,
                module_rollup_cache_key,
                store_global_rollup,
            )

            rollup_key = module_rollup_cache_key(module_name, mod_patches)
            cached_rollup = lookup_global_rollup(module_name, rollup_key)
            if isinstance(cached_rollup, dict) and cached_rollup.get("analysis"):
                analysis = cached_rollup["analysis"]
                print(f"[MODULE] 单次分析命中全局缓存: {module_name}", flush=True)
            else:
                high_risk_evidence = build_high_risk_evidence(mod_patches, repo_dir)
                risk_index = _build_module_risk_index(mod_patches)
                analysis = generate_module_analysis(
                    task,
                    module_name,
                    mod_patches,
                    stats,
                    code_tree,
                    diff_stat,
                    digest,
                    module_diff=module_diff,
                    module_description=module_desc,
                    high_risk_evidence=high_risk_evidence,
                    risk_index=risk_index,
                )
                store_global_rollup(rollup_key, analysis, module_name=module_name)
            coverage = _coverage_for_single_pass(mod_patches, module_diff)
        else:
            analysis = _script_module_analysis(module_name, mod_patches, stats, code_tree)
            coverage = {
                "chunk_count": 1,
                "covered_patch_count": len(mod_patches),
                "total_patch_count": len(mod_patches),
                "truncated_chunk_count": 0,
                "split_exhausted_count": 0,
                "auto_split": False,
                "high_risk_patch_count": sum(
                    1 for p in mod_patches if patch_high_risk_reason(p)
                ),
                "patch_coverage_complete": True,
                "coverage_complete": True,
            }

        return module_name, {
            "module": module_name,
            "description": module_desc or get_dev_module_descriptions().get(module_name, ""),
            "stats": stats,
            "code_tree": code_tree,
            "diff_stat": diff_stat,
            "module_diff_available": bool(module_diff and not module_diff.startswith("(")),
            "analysis": analysis,
            "coverage": coverage,
            "chunk_summaries": chunk_summaries,
            "patch_shas": [patch_sha(p)[:12] for p in mod_patches if patch_sha(p)],
            "_chunk_cache_entries": chunk_cache_entries,
        }

    if progress_cb:
        progress_cb(0, len(modules), f"分模块分析 0/{len(modules)}…")

    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        futures = {pool.submit(_analyze_one, item): item[0] for item in modules}
        done = 0
        for fut in as_completed(futures):
            module_name, payload = fut.result()
            cache_entries = payload.pop("_chunk_cache_entries", None)
            if cache_entries:
                pending_chunk_cache[module_name] = cache_entries
            results[module_name] = payload
            done += 1
            if progress_cb:
                progress_cb(
                    done, len(modules),
                    f"分模块分析 {done}/{len(modules)}：{module_name}",
                )

    if pending_chunk_cache:
        apply_chunk_cache_batch(task_id, pending_chunk_cache)

    total_chunks = sum(
        int((mod.get("coverage") or {}).get("chunk_count") or 1)
        for mod in results.values()
    )
    coverage_complete = all(
        (mod.get("coverage") or {}).get("coverage_complete", True)
        for mod in results.values()
    )
    summary_doc = {
        "module_count": len(results),
        "total_patches": len(patches),
        "total_chunks": total_chunks,
        "coverage_complete": coverage_complete,
        "modules": results,
    }
    update_task(task_id, module_summaries=json.dumps(summary_doc, ensure_ascii=False))
    print(
        f"[MODULE] 模块分析完成: {len(results)} 个模块, {len(patches)} 笔 patch",
        flush=True,
    )
    return summary_doc
