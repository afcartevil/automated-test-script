"""Generate offline, Gerrit-style static HTML reports per module for Feishu delivery."""
from __future__ import annotations

import html
import json
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from web_app.app_paths import outputs_dir
from web_app.database import get_task, get_task_patches
from web_app.dev_module_classifier import get_dev_module_names
from web_app.module_chunk_service import get_patch_diff_text

# Soft limits so a large GKI upgrade still opens in a browser.
_MAX_DIFF_CHARS_PER_PATCH = 120_000
_MAX_DIFF_CHARS_PER_MODULE = 2_500_000
_MAX_PATCHES_WITH_DIFF = 80
_MAX_MERGED_FILES = 200
_MAX_CHARS_PER_FILE = 80_000
_GIT_PATH_CHUNK = 40


def esc(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def module_slug(name: str) -> str:
    text = re.sub(r"[^\w\u4e00-\u9fff\-]+", "_", str(name or "module").strip(), flags=re.UNICODE)
    text = text.strip("_") or "module"
    return text[:80]


@dataclass
class ModuleReportMeta:
    name: str
    slug: str
    patch_count: int
    html_name: str
    html_path: Path
    file_token: str = ""
    file_url: str = ""


@dataclass
class ModuleDiffReportResult:
    task_id: str
    title: str
    report_dir: Path
    index_path: Path
    zip_path: Optional[Path] = None
    modules: List[ModuleReportMeta] = field(default_factory=list)
    subtags: List[ModuleReportMeta] = field(default_factory=list)
    zip_token: str = ""
    zip_url: str = ""
    folder_token: str = ""
    folder_url: str = ""


def build_module_diff_report(
    task_id: str,
    *,
    refresh_diffs: bool = False,
    write_zip: bool = False,
) -> ModuleDiffReportResult:
    """Build index + per-module/subtag HTML under outputs/module_diff_reports/<task_id>/.

    By default does **not** create a zip (Feishu export only needs HTML files + folder).
    Pass ``write_zip=True`` only when an offline pack is explicitly requested.
    """
    task = get_task(task_id)
    if not task:
        raise FileNotFoundError("任务不存在")

    from web_app.checklist_export_service import (
        _hydrate_patch,
        _iter_incremental_subtags,
        _load_json_field,
        _group_patches,
    )
    from web_app.repo_config import get_local_repo_dir

    patches = [_hydrate_patch(row) for row in get_task_patches(task_id)]
    if not patches and task.get("type") != "range":
        raise ValueError("暂无分析结果，无法生成模块代码报告")

    repo_dir = None
    try:
        local = get_local_repo_dir()
        repo_dir = Path(local) if local else None
    except Exception:
        repo_dir = None
    _ = refresh_diffs  # API compat; merged view uses range diff / stored diffs

    modules_doc = _load_json_field(task.get("module_summaries")) or {}
    modules_map = modules_doc.get("modules") or {}
    grouped = _group_patches(patches)

    names = list(get_dev_module_names())
    extra = [n for n in grouped if n not in names]
    ordered = [n for n in (names + extra) if grouped.get(n)]

    from_tag = str(task.get("from_tag") or "").strip()
    to_tag = str(task.get("to_tag") or "").strip()
    from web_app.feishu_service import task_run_stamp

    stamp = task_run_stamp(task)
    title = f"GKI模块代码详情_{from_tag or 'from'}_{to_tag or 'to'}"
    if stamp:
        title = f"{title}_{stamp}"
    report_dir = outputs_dir("module_diff_reports", task_id)
    modules_dir = report_dir / "modules"
    subtags_dir = report_dir / "subtags"
    modules_dir.mkdir(parents=True, exist_ok=True)
    subtags_dir.mkdir(parents=True, exist_ok=True)

    metas: List[ModuleReportMeta] = []
    for name in ordered:
        mod_patches = grouped.get(name) or []
        analysis = {}
        entry = modules_map.get(name)
        if isinstance(entry, dict):
            analysis = entry.get("analysis") or {}
        slug = module_slug(name)
        html_name = f"{slug}.html"
        html_path = modules_dir / html_name
        html_path.write_text(
            _render_module_html(
                task,
                module_name=name,
                patches=mod_patches,
                analysis=analysis if isinstance(analysis, dict) else {},
                repo_dir=repo_dir,
                crumb_href="../index.html",
                page_kind="模块",
            ),
            encoding="utf-8",
        )
        metas.append(
            ModuleReportMeta(
                name=name,
                slug=slug,
                patch_count=len(mod_patches),
                html_name=html_name,
                html_path=html_path,
            )
        )

    subtag_metas: List[ModuleReportMeta] = []
    for sub in _iter_incremental_subtags(task, patches):
        sub_tag = str(sub.get("to_tag") or "").strip()
        sub_patches = list(sub.get("patches") or [])
        if not sub_tag or not sub_patches:
            continue
        slug = module_slug(f"subtag_{sub_tag}")
        html_name = f"{slug}.html"
        html_path = subtags_dir / html_name
        # 子 tag 页只用该增量内 patch 的合并 diff，避免误用整段 from..to
        html_path.write_text(
            _render_module_html(
                task,
                module_name=f"子tag · {sub_tag}",
                patches=sub_patches,
                analysis={
                    "modification_interpretation": (
                        f"子 tag「{sub_tag}」增量共 {len(sub_patches)} 笔 patch，"
                        "以下按文件合并展示本增量全部变更。"
                    ),
                },
                repo_dir=None,
                crumb_href="../index.html",
                page_kind="子tag",
            ),
            encoding="utf-8",
        )
        subtag_metas.append(
            ModuleReportMeta(
                name=sub_tag,
                slug=slug,
                patch_count=len(sub_patches),
                html_name=html_name,
                html_path=html_path,
            )
        )

    index_path = report_dir / "index.html"
    index_path.write_text(
        _render_index_html(task, metas, subtags=subtag_metas, relative_prefix="modules/"),
        encoding="utf-8",
    )
    readme = report_dir / "README.txt"
    readme.write_text(
        "\n".join([
            "GKI 模块代码详情报告（离线打开）",
            f"任务: {task_id}",
            f"版本: {from_tag} -> {to_tag}",
            "",
            "使用方法：",
            "1. 解压本目录/压缩包",
            "2. 用浏览器打开 index.html",
            "3. 总包按模块打开详情；子 tag 整段共用一个详情页（含该增量全部 patch）",
            "",
            "说明：若本机配置了 kernel 仓库，模块页优先用 from_tag..to_tag 对模块文件做净 diff；",
            "子 tag 页按该增量 patch 合并展示。超大文件可能被截断。",
        ]),
        encoding="utf-8",
    )

    zip_path: Optional[Path] = None
    if write_zip:
        zip_path = report_dir / f"{title}.zip"
        _write_zip(zip_path, report_dir, metas, index_path, readme, subtags=subtag_metas)

    return ModuleDiffReportResult(
        task_id=task_id,
        title=title,
        report_dir=report_dir,
        index_path=index_path,
        zip_path=zip_path,
        modules=metas,
        subtags=subtag_metas,
    )


def upload_module_diff_report(
    report: ModuleDiffReportResult,
    *,
    folder_token: str = "",
    folder_url: str = "",
) -> ModuleDiffReportResult:
    """Upload index + per-module/subtag HTML into an existing Feishu Drive folder (no zip)."""
    from web_app.feishu_service import ensure_task_result_folder, normalize_folder_token, upload_drive_file

    target = normalize_folder_token(folder_token)
    url = (folder_url or "").strip()
    if not target:
        task = get_task(report.task_id) or {}
        from web_app.feishu_service import task_run_stamp

        folder = ensure_task_result_folder(
            str(task.get("from_tag") or ""),
            str(task.get("to_tag") or ""),
            run_stamp=task_run_stamp(task),
        )
        target = folder.get("token") or ""
        url = folder.get("url") or url
    report.folder_token = target
    report.folder_url = url or (
        f"https://transsioner.feishu.cn/drive/folder/{target}" if target else ""
    )
    if not target:
        raise RuntimeError("未指定飞书文件夹，无法上传模块代码详情")

    for meta in report.modules:
        info = upload_drive_file(
            meta.html_path,
            folder_token=report.folder_token,
            name=f"{meta.slug}.html",
        )
        meta.file_token = info.get("token") or ""
        meta.file_url = info.get("url") or ""

    for meta in report.subtags:
        info = upload_drive_file(
            meta.html_path,
            folder_token=report.folder_token,
            name=f"{meta.slug}.html",
        )
        meta.file_token = info.get("token") or ""
        meta.file_url = info.get("url") or ""

    # Rewrite index with absolute Feishu file URLs when available.
    if any(m.file_url for m in report.modules) or any(m.file_url for m in report.subtags):
        task = get_task(report.task_id) or {}
        report.index_path.write_text(
            _render_index_html(
                task,
                report.modules,
                subtags=report.subtags,
                relative_prefix="modules/",
                use_uploaded_urls=True,
            ),
            encoding="utf-8",
        )
        try:
            upload_drive_file(
                report.index_path,
                folder_token=report.folder_token,
                name="index.html",
            )
        except Exception as exc:
            print(f"[FEISHU] 上传 index.html 失败: {exc}", flush=True)

    return report


def module_url_map(report: ModuleDiffReportResult) -> Dict[str, str]:
    return {m.name: m.file_url for m in report.modules if m.file_url}


def subtag_url_map(report: ModuleDiffReportResult) -> Dict[str, str]:
    """Map sub-tag name (to_tag) → uploaded HTML URL."""
    return {m.name: m.file_url for m in report.subtags if m.file_url}


def _write_zip(
    zip_path: Path,
    report_dir: Path,
    metas: Sequence[ModuleReportMeta],
    index_path: Path,
    readme: Path,
    *,
    subtags: Optional[Sequence[ModuleReportMeta]] = None,
) -> None:
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(index_path, arcname="index.html")
        zf.write(readme, arcname="README.txt")
        for meta in metas:
            zf.write(meta.html_path, arcname=f"modules/{meta.html_name}")
        for meta in subtags or []:
            zf.write(meta.html_path, arcname=f"subtags/{meta.html_name}")


def _patch_files(patch: Dict[str, Any]) -> List[str]:
    files = patch.get("files") or []
    if isinstance(files, list):
        return [str(f) for f in files if f]
    if isinstance(files, str) and files.strip():
        return [files.strip()]
    return []


def _commit_urls(task: Dict[str, Any], sha: str) -> Tuple[str, str]:
    repo = str(task.get("repo") or "https://android.googlesource.com/kernel/common").rstrip("/")
    if repo.endswith(".git"):
        repo = repo[:-4]
    sha = (sha or "").strip()
    if not sha:
        return "", ""
    return f"{repo}/+/{sha}", f"{repo}/+/{sha}^!"


def _normalize_diff_path(path: str) -> str:
    text = (path or "").strip()
    if text.startswith(("a/", "b/")):
        text = text[2:]
    if text in ("/dev/null", "dev/null"):
        return ""
    return text.replace("\\", "/")


def _diff_line_stats(diff_text: str) -> Tuple[int, int]:
    added = deleted = 0
    for line in diff_text.splitlines():
        if line.startswith("+++") or line.startswith("---") or line.startswith("@@") or line.startswith("diff "):
            continue
        if line.startswith("+"):
            added += 1
        elif line.startswith("-"):
            deleted += 1
    return added, deleted


def _render_file_diff_body(file_diff: str) -> str:
    lines_html: List[str] = []
    for raw in file_diff.splitlines():
        css = "ctx"
        if raw.startswith("+++ ") or raw.startswith("--- ") or raw.startswith("diff ") or raw.startswith("index "):
            css = "meta"
        elif raw.startswith("@@"):
            css = "hunk"
        elif raw.startswith("+"):
            css = "add"
        elif raw.startswith("-"):
            css = "del"
        lines_html.append(
            f'<div class="diff-line {css}"><span class="gutter"></span>'
            f"<code>{esc(raw)}</code></div>"
        )
    return "".join(lines_html)


def _render_diff_html(diff_text: str, *, truncated: bool = False) -> str:
    if not diff_text.strip():
        return '<div class="empty">无 diff 内容（分析结果未保存 diff，且本机仓库未能补全）</div>'

    from web_app.diff_processor import split_unified_diff_by_file

    parts = split_unified_diff_by_file(diff_text)
    if not parts:
        parts = [("", diff_text)]

    blocks: List[str] = []
    for path, file_diff in parts:
        path_label = _normalize_diff_path(path) or path or "diff"
        note = '<div class="trunc-note">⚠ 本文件/本 patch diff 已截断</div>' if truncated else ""
        blocks.append(
            f'<section class="file-block" id="f-{esc(module_slug(path_label))}">'
            f'<div class="file-path">{esc(path_label)}</div>'
            f'{note}<div class="diff-body">{_render_file_diff_body(file_diff)}</div></section>'
        )
    return "".join(blocks)


def _module_file_paths(patches: Sequence[Dict[str, Any]]) -> List[str]:
    seen: set = set()
    out: List[str] = []
    for patch in patches:
        for path in _patch_files(patch):
            norm = _normalize_diff_path(path)
            if not norm or norm in seen:
                continue
            seen.add(norm)
            out.append(norm)
    return out


def _git_merged_diff_by_file(
    repo_dir: Path,
    from_tag: str,
    to_tag: str,
    files: Sequence[str],
) -> Dict[str, str]:
    """Net ``from_tag..to_tag`` diff for selected paths, keyed by file path."""
    if not repo_dir or not from_tag or not to_tag or not files:
        return {}
    try:
        from tools.patch_analyzer import run_git
        from web_app.diff_processor import split_unified_diff_by_file
    except Exception:
        return {}

    chunks: List[str] = []
    paths = list(files)[:_MAX_MERGED_FILES]
    for i in range(0, len(paths), _GIT_PATH_CHUNK):
        batch = paths[i:i + _GIT_PATH_CHUNK]
        try:
            text = run_git(
                Path(repo_dir),
                ["diff", "--no-color", "--find-renames", f"{from_tag}..{to_tag}", "--", *batch],
            )
        except Exception:
            continue
        if text and text.strip():
            chunks.append(text)
    if not chunks:
        return {}

    merged: Dict[str, str] = {}
    for chunk in chunks:
        for path, file_diff in split_unified_diff_by_file(chunk):
            key = _normalize_diff_path(path) or path or "diff"
            if not key:
                continue
            # Prefer later chunk content if duplicate (should be rare).
            merged[key] = file_diff
    return merged


def _aggregate_patch_diffs_by_file(
    patches: Sequence[Dict[str, Any]],
    repo_dir: Optional[Path],
) -> Dict[str, List[Tuple[str, str, str]]]:
    """Fallback: group stored patch diffs by file → [(sha, title, file_diff), ...]."""
    from web_app.diff_processor import split_unified_diff_by_file

    by_file: Dict[str, List[Tuple[str, str, str]]] = {}
    budget = _MAX_DIFF_CHARS_PER_MODULE
    for idx, patch in enumerate(patches):
        if idx >= _MAX_PATCHES_WITH_DIFF or budget < 2000:
            break
        sha = str(patch.get("sha") or patch.get("commit") or "")[:12]
        title = str(patch.get("title") or "")[:80]
        raw = get_patch_diff_text(patch, repo_dir, max_chars=min(_MAX_DIFF_CHARS_PER_PATCH, budget))
        if not raw.strip():
            continue
        budget -= len(raw)
        parts = split_unified_diff_by_file(raw) or [("", raw)]
        for path, file_diff in parts:
            key = _normalize_diff_path(path) or path or f"(patch-{sha})"
            by_file.setdefault(key, []).append((sha, title, file_diff))
    return by_file


def _build_merged_file_sections(
    task: Dict[str, Any],
    patches: Sequence[Dict[str, Any]],
    repo_dir: Optional[Path],
) -> Tuple[str, str, str]:
    """Return (mode_note, file_nav_html, files_html) for Gerrit-style merged view."""
    files = _module_file_paths(patches)
    from_tag = str(task.get("from_tag") or "").strip()
    to_tag = str(task.get("to_tag") or "").strip()

    net_by_file: Dict[str, str] = {}
    mode = "stored"
    if repo_dir and from_tag and to_tag and files:
        net_by_file = _git_merged_diff_by_file(Path(repo_dir), from_tag, to_tag, files)
        if net_by_file:
            mode = "git-range"

    nav_items: List[str] = []
    blocks: List[str] = []
    total_chars = 0
    shown = 0

    if mode == "git-range":
        mode_note = (
            f'<div class="banner">已按文件合并展示：<code>{esc(from_tag)}..{esc(to_tag)}</code> '
            f"的净变更（类似 Gerrit Change 文件列表），共 {len(net_by_file)} 个文件。</div>"
        )
        ordered_paths = sorted(net_by_file.keys())
        for path in ordered_paths:
            if shown >= _MAX_MERGED_FILES or total_chars >= _MAX_DIFF_CHARS_PER_MODULE:
                break
            file_diff = net_by_file[path]
            truncated = False
            if len(file_diff) > _MAX_CHARS_PER_FILE:
                file_diff = file_diff[:_MAX_CHARS_PER_FILE] + "\n... (file truncated) ..."
                truncated = True
            add_n, del_n = _diff_line_stats(file_diff)
            anchor = module_slug(path)
            nav_items.append(
                f'<a href="#f-{esc(anchor)}" class="file-nav-item">'
                f'<span class="path">{esc(path)}</span>'
                f'<span class="stat"><span class="add">+{add_n}</span> '
                f'<span class="del">-{del_n}</span></span></a>'
            )
            note = '<div class="trunc-note">⚠ 本文件 diff 已截断</div>' if truncated else ""
            blocks.append(
                f'<section class="file-block" id="f-{esc(anchor)}">'
                f'<div class="file-path">{esc(path)}'
                f'<span class="file-stat">+{add_n} / -{del_n}</span></div>'
                f'{note}<div class="diff-body">{_render_file_diff_body(file_diff)}</div></section>'
            )
            total_chars += len(file_diff)
            shown += 1
    else:
        mode_note = (
            '<div class="banner">未拿到 tag 区间净 diff（本机未配置仓库或 git diff 失败），'
            "已按文件汇总各 patch 的 diff；同一文件多笔修改会按提交分段展示。</div>"
        )
        by_file = _aggregate_patch_diffs_by_file(patches, repo_dir)
        if not by_file and files:
            # Still show file list without bodies
            for path in files[:_MAX_MERGED_FILES]:
                nav_items.append(
                    f'<a href="#f-{esc(module_slug(path))}" class="file-nav-item">'
                    f'<span class="path">{esc(path)}</span></a>'
                )
                blocks.append(
                    f'<section class="file-block" id="f-{esc(module_slug(path))}">'
                    f'<div class="file-path">{esc(path)}</div>'
                    f'<div class="empty">无可用 diff 文本</div></section>'
                )
        for path in sorted(by_file.keys()):
            if shown >= _MAX_MERGED_FILES or total_chars >= _MAX_DIFF_CHARS_PER_MODULE:
                break
            entries = by_file[path]
            combined_parts: List[str] = []
            for sha, title, file_diff in entries:
                header = f"@@ commit {sha} — {title} @@"
                piece = file_diff
                if len(piece) > _MAX_CHARS_PER_FILE // max(1, len(entries)):
                    piece = piece[: _MAX_CHARS_PER_FILE // max(1, len(entries))] + "\n... (truncated) ..."
                combined_parts.append(f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n{header}\n{piece}")
            combined = "\n".join(combined_parts)
            if len(combined) > _MAX_CHARS_PER_FILE:
                combined = combined[:_MAX_CHARS_PER_FILE] + "\n... (file truncated) ..."
            add_n, del_n = _diff_line_stats(combined)
            anchor = module_slug(path)
            nav_items.append(
                f'<a href="#f-{esc(anchor)}" class="file-nav-item">'
                f'<span class="path">{esc(path)}</span>'
                f'<span class="stat"><span class="add">+{add_n}</span> '
                f'<span class="del">-{del_n}</span></span></a>'
            )
            # Render each commit segment separately for readability
            body_parts: List[str] = []
            for sha, title, file_diff in entries:
                piece = file_diff
                trunc = False
                limit = _MAX_CHARS_PER_FILE // max(1, len(entries))
                if len(piece) > limit:
                    piece = piece[:limit] + "\n... (truncated) ..."
                    trunc = True
                body_parts.append(
                    f'<div class="commit-seg"><div class="commit-seg-head">'
                    f'<code>{esc(sha)}</code> {esc(title)}</div>'
                    f'{"<div class=trunc-note>⚠ 已截断</div>" if trunc else ""}'
                    f'<div class="diff-body">{_render_file_diff_body(piece)}</div></div>'
                )
                total_chars += len(piece)
            blocks.append(
                f'<section class="file-block" id="f-{esc(anchor)}">'
                f'<div class="file-path">{esc(path)}'
                f'<span class="file-stat">+{add_n} / -{del_n} · {len(entries)} commits</span></div>'
                f'{"".join(body_parts)}</section>'
            )
            shown += 1

    if not blocks:
        return mode_note, "", '<div class="empty">本模块无可展示的文件变更</div>'

    omitted = ""
    if len(files) > shown:
        omitted = f'<div class="hint">仅展示前 {shown} 个文件（共涉及约 {len(files)} 个）。</div>'

    nav = (
        f'<nav class="file-nav"><div class="file-nav-title">Files ({shown})</div>'
        f'{"".join(nav_items)}</nav>'
    )
    return mode_note, nav, omitted + "".join(blocks)


def _format_prose(text: Any) -> str:
    """Render multi-line analysis text with paragraphs / simple bullets."""
    raw = str(text or "").strip()
    if not raw:
        return '<div class="empty">暂无</div>'
    blocks: List[str] = []
    buf: List[str] = []

    def flush_para() -> None:
        nonlocal buf
        if not buf:
            return
        blocks.append("<p>" + "<br>".join(esc(x) for x in buf) + "</p>")
        buf = []

    for line in raw.splitlines():
        s = line.rstrip()
        if not s.strip():
            flush_para()
            continue
        bullet = re.match(r"^\s*(?:[-*•]|\d+[.)])\s+(.*)$", s)
        if bullet:
            flush_para()
            blocks.append(f"<li>{esc(bullet.group(1))}</li>")
            continue
        buf.append(s.strip())
    flush_para()
    html = "".join(blocks)
    # Wrap consecutive <li> into <ul>
    html = re.sub(r"(?:<li>.*?</li>)+", lambda m: f"<ul>{m.group(0)}</ul>", html)
    return f'<div class="prose">{html}</div>'


def _index_patches_by_sha(patches: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for p in patches:
        sha = str(p.get("sha") or p.get("commit") or "").strip()
        if not sha:
            continue
        out[sha] = p
        out[sha[:12]] = p
    return out


def _patch_source_links(task: Dict[str, Any], sha: str, patch: Optional[Dict[str, Any]] = None) -> Tuple[str, str]:
    commit_url, diff_url = _commit_urls(task, sha)
    if patch:
        if patch.get("commit_url"):
            commit_url = str(patch.get("commit_url"))
        if patch.get("diff_url"):
            diff_url = str(patch.get("diff_url"))
    return commit_url, diff_url


def _unique_lines(lines: Sequence[str], *, limit: int = 40) -> List[str]:
    out: List[str] = []
    seen = set()
    for raw in lines:
        text = str(raw or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
        if len(out) >= limit:
            break
    return out


def _patch_brief(patch: Dict[str, Any]) -> str:
    for key in ("problem_solved", "modification_interpretation", "key_risk"):
        text = str(patch.get(key) or "").strip()
        if text:
            return text
    rich = patch.get("commit_interpretation_rich") or {}
    if isinstance(rich, dict):
        text = str(rich.get("summary") or "").strip()
        if text:
            return text
    return str(patch.get("title") or "").strip()


def _module_stats_banner(analysis: Dict[str, Any], patches: Sequence[Dict[str, Any]]) -> str:
    n = len(patches)
    blocked = sum(1 for p in patches if p.get("blocked"))
    elev = sum(
        1
        for p in patches
        if str(p.get("crash_risk") or "").strip() in ("中", "高")
    )
    high_n = 0
    high = analysis.get("high_risk_patches") or []
    if isinstance(high, list) and high:
        high_n = len(high)
    else:
        high_n = blocked + elev
    scores = []
    for p in patches:
        try:
            scores.append(float(p.get("score")))
        except (TypeError, ValueError):
            continue
    avg = f"{sum(scores) / len(scores):.1f}" if scores else "-"
    files = set()
    for p in patches:
        files.update(_patch_files(p))
    bits = [
        f'<span class="stat-pill"><b>{n}</b> 笔 patch</span>',
        f'<span class="stat-pill"><b>{len(files)}</b> 个文件</span>',
        f'<span class="stat-pill">均分 <b>{esc(avg)}</b></span>',
        f'<span class="stat-pill">高风险 <b>{high_n}</b></span>',
        f'<span class="stat-pill">死机中/高 <b>{elev}</b></span>',
    ]
    if blocked:
        bits.append(f'<span class="stat-pill warn">blocked <b>{blocked}</b></span>')
    crash = str(analysis.get("crash_risk") or "").strip()
    if crash:
        bits.append(f'<span class="stat-pill">模块死机风险 <b>{esc(crash)}</b></span>')
    return f'<div class="stats-banner">{"".join(bits)}</div>'


def _enrich_modification(analysis: Dict[str, Any], patches: Sequence[Dict[str, Any]]) -> str:
    parts: List[str] = []
    base = str(analysis.get("modification_interpretation") or "").strip()
    if base:
        parts.append(base)

    themes: Dict[str, int] = {}
    for p in patches:
        title = str(p.get("title") or "").strip()
        if not title:
            continue
        # crude theme: first path-ish token or first 2 words
        head = re.split(r"[:：\-\s]+", title, maxsplit=1)[0].strip()[:24]
        if head:
            themes[head] = themes.get(head, 0) + 1
    if themes:
        top = sorted(themes.items(), key=lambda x: (-x[1], x[0]))[:12]
        parts.append("变更主题分布：\n" + "\n".join(f"• {k}（{v} 笔）" for k, v in top))

    briefs = []
    for p in patches[:25]:
        sha = str(p.get("sha") or p.get("commit") or "")[:12]
        brief = _patch_brief(p)
        title = str(p.get("title") or "").strip()
        if not brief and not title:
            continue
        line = f"• [{sha}] {title}" if title else f"• [{sha}]"
        if brief and brief != title:
            line += f"：{brief}"
        briefs.append(line)
    if briefs:
        parts.append("代表性 patch 解读：\n" + "\n".join(_unique_lines(briefs, limit=20)))

    return "\n\n".join(parts).strip()


def _enrich_impact(analysis: Dict[str, Any], patches: Sequence[Dict[str, Any]]) -> str:
    parts: List[str] = []
    base = str(analysis.get("impact_scope") or "").strip()
    if base:
        parts.append(base)

    crash = str(analysis.get("crash_risk") or "").strip()
    crash_reason = str(analysis.get("crash_risk_reason") or "").strip()
    if crash or crash_reason:
        line = f"模块死机风险：{crash or '未标注'}"
        if crash_reason:
            line += f"\n{crash_reason}"
        parts.append(line)

    files = []
    for p in patches:
        files.extend(_patch_files(p))
    uniq_files = _unique_lines(files, limit=40)
    if uniq_files:
        shown = uniq_files[:25]
        more = len(uniq_files) - len(shown)
        file_block = "涉及文件（节选）：\n" + "\n".join(f"• {f}" for f in shown)
        if more > 0:
            file_block += f"\n• … 另有 {more} 个文件见下方代码变更"
        parts.append(file_block)

    risk_lines = []
    for p in patches:
        if not (p.get("blocked") or str(p.get("crash_risk") or "").strip() in ("中", "高")):
            continue
        sha = str(p.get("sha") or p.get("commit") or "")[:12]
        title = str(p.get("title") or "").strip()
        why = str(
            p.get("key_risk") or p.get("crash_risk_reason") or p.get("recommendation") or ""
        ).strip()
        risk_lines.append(f"• [{sha}] {title}" + (f"：{why}" if why else ""))
    if risk_lines:
        parts.append("需重点关注：\n" + "\n".join(_unique_lines(risk_lines, limit=15)))

    return "\n\n".join(parts).strip()


def _enrich_test_suggestions(analysis: Dict[str, Any], patches: Sequence[Dict[str, Any]]) -> str:
    text = str(analysis.get("test_suggestions") or "").strip()
    extras: List[str] = []
    checklist = analysis.get("verification_checklist") or []
    if isinstance(checklist, list):
        for item in checklist[:40]:
            line = str(item or "").strip()
            if line:
                extras.append(f"• {line}")
    if not text and not extras:
        for p in patches[:20]:
            raw = p.get("llm_test_suggestions") or p.get("test_suggestions")
            if isinstance(raw, dict):
                for key in ("must", "should", "optional", "建议", "必测"):
                    val = raw.get(key)
                    if isinstance(val, list):
                        for item in val[:6]:
                            if str(item).strip():
                                extras.append(f"• {str(item).strip()}")
                    elif str(val or "").strip():
                        extras.append(f"• {str(val).strip()}")
            elif str(raw or "").strip():
                extras.append(f"• {str(raw).strip()}")
        return "\n".join(_unique_lines(extras, limit=40))
    if extras:
        return (text + "\n\n验证清单：\n" + "\n".join(_unique_lines(extras, limit=40))).strip()
    return text


def _module_analysis_top(
    task: Dict[str, Any],
    analysis: Dict[str, Any],
    patches: Sequence[Dict[str, Any]],
) -> str:
    """Full-width top summary: 修改解读 / 影响范围 / 测试建议 (+ optional extras)."""
    modification = _enrich_modification(analysis, patches)
    impact = _enrich_impact(analysis, patches)
    tests = _enrich_test_suggestions(analysis, patches)
    closure = str(
        analysis.get("problem_closure_summary") or analysis.get("problem_solved") or ""
    ).strip()
    cross = str(analysis.get("cross_module_notes") or "").strip()
    banner = _module_stats_banner(analysis, patches)

    cards = [
        ("修改解读", modification or "暂无模块级修改解读"),
        ("影响范围", impact or "暂无影响范围说明"),
        ("测试建议", tests or "暂无测试建议"),
    ]
    cards_html = "".join(
        f'<section class="summary-card"><h3>{esc(title)}</h3>{_format_prose(body)}</section>'
        for title, body in cards
    )

    extras: List[str] = []
    if closure:
        extras.append(
            f'<section class="summary-card summary-card-wide"><h3>问题闭环</h3>{_format_prose(closure)}</section>'
        )
    if cross:
        extras.append(
            f'<section class="summary-card summary-card-wide"><h3>跨模块说明</h3>{_format_prose(cross)}</section>'
        )

    changes = analysis.get("code_changes") or []
    if isinstance(changes, list) and changes:
        rows = []
        for item in changes[:60]:
            if not isinstance(item, dict):
                continue
            loc = str(item.get("location") or "").strip()
            exp = str(item.get("explanation") or "").strip()
            risk = str(item.get("risk_level") or "").strip()
            rows.append(
                "<tr>"
                f"<td><code>{esc(loc)}</code></td>"
                f"<td>{esc(exp)}</td>"
                f"<td>{esc(risk or '-')}</td>"
                "</tr>"
            )
        if rows:
            extras.append(
                '<section class="summary-card summary-card-wide"><h3>关键代码变化</h3>'
                '<table class="detail-table"><thead><tr><th>位置</th><th>说明</th><th>风险</th></tr></thead>'
                f'<tbody>{"".join(rows)}</tbody></table></section>'
            )

    return (
        f'<section class="summary-band">{banner}'
        f'<div class="summary-grid">{cards_html}</div>'
        f'{"".join(extras)}</section>'
    )


def _render_high_risk_section(
    task: Dict[str, Any],
    analysis: Dict[str, Any],
    patches: Sequence[Dict[str, Any]],
) -> str:
    high = analysis.get("high_risk_patches") or []
    by_sha = _index_patches_by_sha(patches)
    # Also surface blocked / elevated crash patches if analysis list is empty
    if not isinstance(high, list) or not high:
        high = []
        for p in patches:
            if p.get("blocked") or str(p.get("crash_risk") or "").strip() in ("中", "高"):
                high.append({
                    "sha": p.get("sha") or p.get("commit"),
                    "title": p.get("title"),
                    "reason": p.get("key_risk") or p.get("crash_risk_reason") or p.get("recommendation"),
                })

    items: List[str] = []
    seen: set = set()
    for item in high[:60]:
        if not isinstance(item, dict):
            continue
        sha = str(item.get("sha") or item.get("commit") or "").strip()
        if not sha or sha in seen:
            continue
        seen.add(sha)
        patch = by_sha.get(sha) or by_sha.get(sha[:12])
        title = str(item.get("title") or (patch or {}).get("title") or "").strip()
        reason = str(
            item.get("reason") or item.get("risk") or item.get("key_risk") or ""
        ).strip()
        if not reason and patch:
            reason = str(
                patch.get("key_risk")
                or patch.get("crash_risk_reason")
                or patch.get("recommendation")
                or ""
            ).strip()
        full_sha = str((patch or {}).get("sha") or (patch or {}).get("commit") or sha).strip()
        commit_url, diff_url = _patch_source_links(task, full_sha or sha, patch)
        if not commit_url and not diff_url and full_sha:
            commit_url, diff_url = _commit_urls(task, full_sha)
        links = []
        if commit_url:
            links.append(
                f'<a href="{esc(commit_url)}" target="_blank" rel="noopener">原始 Commit</a>'
            )
        if diff_url:
            links.append(
                f'<a href="{esc(diff_url)}" target="_blank" rel="noopener">原始 Diff</a>'
            )
        link_html = (" · ".join(links)) if links else '<span class="muted">无可用原始链接</span>'
        score = ""
        if patch and patch.get("score") is not None:
            try:
                score = f"{float(patch.get('score')):.1f}"
            except (TypeError, ValueError):
                score = str(patch.get("score"))
        meta_bits = []
        if score:
            meta_bits.append(f"score {esc(score)}")
        if patch and patch.get("recommendation"):
            meta_bits.append(esc(str(patch.get("recommendation"))))
        if patch and patch.get("crash_risk"):
            meta_bits.append(f"死机风险 {esc(patch.get('crash_risk'))}")
        if patch and patch.get("blocked"):
            meta_bits.append("blocked")
        meta = (" · ".join(meta_bits)) if meta_bits else ""
        detail_bits = []
        if reason:
            detail_bits.append(f"<div class=\"risk-reason\"><b>风险说明：</b>{esc(reason)}</div>")
        if patch:
            crash_reason = str(patch.get("crash_risk_reason") or "").strip()
            if crash_reason and crash_reason != reason:
                detail_bits.append(
                    f"<div class=\"risk-reason\"><b>死机分析：</b>{esc(crash_reason)}</div>"
                )
            brief = _patch_brief(patch)
            if brief and brief not in (reason, title, crash_reason):
                detail_bits.append(
                    f"<div class=\"risk-reason\"><b>变更解读：</b>{esc(brief)}</div>"
                )
            files = _patch_files(patch)
            if files:
                shown = files[:8]
                more = len(files) - len(shown)
                file_txt = ", ".join(esc(f) for f in shown)
                if more > 0:
                    file_txt += f" 等 {len(files)} 个文件"
                detail_bits.append(f'<div class="muted">文件：{file_txt}</div>')
        items.append(
            '<article class="risk-card">'
            f'<div class="risk-card-head"><code>{esc(full_sha[:12] or sha[:12])}</code>'
            f'<span class="risk-title">{esc(title)}</span></div>'
            f'{f"<div class=muted>{meta}</div>" if meta else ""}'
            f'{"".join(detail_bits)}'
            f'<div class="risk-links">{link_html}</div>'
            "</article>"
        )
    if not items:
        return ""
    return (
        '<section class="block">'
        f'<h2>高风险 Patch（{len(items)}）</h2>'
        f'<div class="risk-grid">{"".join(items)}</div>'
        "</section>"
    )


def _render_patch_list(task: Dict[str, Any], patches: Sequence[Dict[str, Any]]) -> str:
    """Commit table with original links and richer per-patch detail."""
    rows: List[str] = []
    for patch in patches:
        sha = str(patch.get("sha") or patch.get("commit") or "").strip()
        title = str(patch.get("title") or "").strip()
        score = patch.get("score")
        try:
            score_txt = f"{float(score):.1f}"
        except (TypeError, ValueError):
            score_txt = "-"
        rec = str(patch.get("recommendation") or "")
        crash = str(patch.get("crash_risk") or "-")
        brief = _patch_brief(patch)
        commit_url, diff_url = _patch_source_links(task, sha, patch)
        link_bits = []
        if commit_url:
            link_bits.append(f'<a href="{esc(commit_url)}" target="_blank" rel="noopener">Commit</a>')
        if diff_url:
            link_bits.append(f'<a href="{esc(diff_url)}" target="_blank" rel="noopener">Diff</a>')
        sha_html = f"<code>{esc(sha[:12])}</code>"
        if link_bits:
            sha_html += "<br>" + " · ".join(link_bits)
        title_html = esc(title)
        if brief and brief != title:
            title_html += f'<div class="muted patch-brief">{esc(brief)}</div>'
        files = _patch_files(patch)
        file_n = len(files)
        rows.append(
            "<tr>"
            f"<td>{sha_html}</td>"
            f"<td>{title_html}</td>"
            f"<td>{esc(score_txt)}</td>"
            f"<td>{esc(rec or '-')}</td>"
            f"<td>{esc(crash)}</td>"
            f"<td>{file_n}</td>"
            "</tr>"
        )
    return (
        '<div class="card card-scroll"><table class="patch-table"><thead><tr>'
        "<th>Commit / 原始链接</th><th>Title / 解读</th><th>Score</th>"
        "<th>建议</th><th>死机</th><th>Files</th>"
        "</tr></thead><tbody>"
        + ("".join(rows) or '<tr><td colspan="6">无 patch</td></tr>')
        + "</tbody></table></div>"
    )


def _render_module_html(
    task: Dict[str, Any],
    *,
    module_name: str,
    patches: Sequence[Dict[str, Any]],
    analysis: Dict[str, Any],
    repo_dir: Optional[Path],
    crumb_href: str = "../index.html",
    page_kind: str = "模块",
) -> str:
    from_tag = esc(task.get("from_tag") or "")
    to_tag = esc(task.get("to_tag") or "")

    sorted_patches = sorted(
        patches,
        key=lambda p: (
            0 if p.get("blocked") else 1,
            -float(p.get("score") or 0) if str(p.get("score") or "").replace(".", "", 1).isdigit() else 0,
            str(p.get("sha") or ""),
        ),
    )

    summary_html = _module_analysis_top(task, analysis, sorted_patches)
    high_risk_html = _render_high_risk_section(task, analysis, sorted_patches)
    mode_note, file_nav, files_html = _build_merged_file_sections(task, sorted_patches, repo_dir)
    patch_table = _render_patch_list(task, sorted_patches)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{esc(module_name)} · {esc(page_kind)}代码详情</title>
<style>{_REPORT_CSS}</style>
</head>
<body>
<div class="page">
  <header class="top">
    <div class="crumb"><a href="{esc(crumb_href)}">← 返回目录</a></div>
    <h1>{esc(module_name)}</h1>
    <div class="sub">{from_tag} → {to_tag} · {len(sorted_patches)} 笔 patch · 按文件合并展示</div>
  </header>

  <section class="block">
    <h2>{esc(page_kind)}分析</h2>
    {summary_html}
  </section>

  {high_risk_html}

  <section class="block">
    <h2>Patch 列表</h2>
    {patch_table}
  </section>

  <section class="block">
    <h2>代码变更（按文件合并）</h2>
    {mode_note}
    <div class="gerrit-layout">
      {file_nav}
      <div class="gerrit-files">{files_html}</div>
    </div>
  </section>
</div>
</body>
</html>
"""


def _render_index_html(
    task: Dict[str, Any],
    metas: Sequence[ModuleReportMeta],
    *,
    subtags: Optional[Sequence[ModuleReportMeta]] = None,
    relative_prefix: str = "modules/",
    use_uploaded_urls: bool = False,
) -> str:
    from_tag = esc(task.get("from_tag") or "")
    to_tag = esc(task.get("to_tag") or "")
    rows = []
    for m in metas:
        href = m.file_url if (use_uploaded_urls and m.file_url) else f"{relative_prefix}{m.html_name}"
        rows.append(
            "<tr>"
            f'<td><a href="{esc(href)}">{esc(m.name)}</a></td>'
            f"<td>{m.patch_count}</td>"
            f'<td><a class="btn" href="{esc(href)}">打开代码详情</a></td>'
            "</tr>"
        )
    sub_rows = []
    for m in subtags or []:
        href = m.file_url if (use_uploaded_urls and m.file_url) else f"subtags/{m.html_name}"
        if use_uploaded_urls and m.file_url:
            href = m.file_url
        sub_rows.append(
            "<tr>"
            f'<td><a href="{esc(href)}">{esc(m.name)}</a></td>'
            f"<td>{m.patch_count}</td>"
            f'<td><a class="btn" href="{esc(href)}">打开子tag详情</a></td>'
            "</tr>"
        )
    sub_section = ""
    if sub_rows:
        sub_section = f"""
  <h2>子 tag 增量详情</h2>
  <p class="hint">每个子 tag 整段共用一个详情页（不再按模块拆分）。</p>
  <table class="mod-table">
    <thead><tr><th>子 tag</th><th>Patch 数</th><th>操作</th></tr></thead>
    <tbody>
      {"".join(sub_rows)}
    </tbody>
  </table>
"""
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>GKI 模块代码详情目录</title>
<style>{_REPORT_CSS}</style>
</head>
<body>
<div class="page">
  <header class="top">
    <h1>GKI 模块代码详情</h1>
    <div class="sub">{from_tag} → {to_tag}</div>
    <p class="hint">总包按模块查看详情；子 tag 整段共用一个详情链接。
    飞书侧请从云盘文件夹打开 index.html 或各模块/子 tag 页面。</p>
  </header>
  <h2>模块详情（总包）</h2>
  <table class="mod-table">
    <thead><tr><th>模块</th><th>Patch 数</th><th>操作</th></tr></thead>
    <tbody>
      {"".join(rows) or '<tr><td colspan="3">无模块数据</td></tr>'}
    </tbody>
  </table>
  {sub_section}
</div>
</body>
</html>
"""


_REPORT_CSS = """
:root {
  --bg: #f4f6f8;
  --panel: #ffffff;
  --text: #1f2937;
  --muted: #6b7280;
  --border: #d7dee7;
  --add-bg: #e6ffec;
  --add-fg: #116329;
  --del-bg: #ffebe9;
  --del-fg: #cf222e;
  --hunk-bg: #ddf4ff;
  --meta-bg: #f6f8fa;
  --accent: #0969da;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.5;
}
.page {
  max-width: min(100%, 2200px);
  margin: 0 auto;
  padding: 16px 20px 48px;
}
@media (min-width: 1280px) {
  .page { padding: 18px 28px 52px; }
}
@media (min-width: 1800px) {
  .page { padding: 20px 36px 56px; }
}
.top h1 { margin: 8px 0 4px; font-size: 26px; }
.sub, .hint, .muted { color: var(--muted); }
.crumb a, a { color: var(--accent); text-decoration: none; }
.crumb a:hover, a:hover { text-decoration: underline; }
.block { margin: 22px 0 28px; }
.block > h2 {
  margin: 0 0 12px;
  font-size: 18px;
  border-bottom: 1px solid var(--border);
  padding-bottom: 8px;
}
.summary-band { margin-bottom: 8px; }
.summary-grid {
  display: grid;
  gap: 14px;
  grid-template-columns: 1fr;
}
@media (min-width: 960px) {
  .summary-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}
.summary-card {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 14px 16px;
  min-height: 180px;
}
.summary-card-wide { margin-top: 14px; min-height: 0; }
.summary-card h3 { margin: 0 0 10px; font-size: 15px; }
.stats-banner {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 0 0 14px;
}
.stat-pill {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 6px 10px;
  background: #eef2f7;
  border: 1px solid var(--border);
  border-radius: 8px;
  font-size: 13px;
  color: var(--text);
}
.stat-pill.warn {
  background: #fff5f3;
  border-color: #f3c1b8;
  color: #9b1c1c;
}
.prose { font-size: 14px; line-height: 1.65; max-height: 420px; overflow: auto; }
.prose p { margin: 0 0 10px; }
.prose ul { margin: 0 0 10px; padding-left: 1.2em; }
.prose li { margin: 4px 0; }
.patch-brief { margin-top: 4px; font-size: 12px; line-height: 1.45; }
.detail-table, .patch-table, .mod-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  background: var(--panel);
}
.detail-table th, .detail-table td,
.patch-table th, .patch-table td,
.mod-table th, .mod-table td {
  padding: 8px 10px;
  border-bottom: 1px solid var(--border);
  text-align: left;
  vertical-align: top;
}
.detail-table th, .patch-table th, .mod-table th { background: #eef2f7; }
.card {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 10px;
}
.card-scroll { max-height: 520px; overflow: auto; }
.risk-grid {
  display: grid;
  gap: 12px;
  grid-template-columns: 1fr;
}
@media (min-width: 900px) {
  .risk-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
.risk-card {
  background: #fff8f6;
  border: 1px solid #f3c1b8;
  border-radius: 10px;
  padding: 12px 14px;
}
.risk-card-head {
  display: flex;
  gap: 10px;
  align-items: baseline;
  flex-wrap: wrap;
  margin-bottom: 6px;
}
.risk-title { font-weight: 600; }
.risk-reason { margin: 8px 0; font-size: 13px; line-height: 1.55; }
.risk-links { font-size: 13px; }
.gerrit-layout { display: grid; gap: 14px; }
@media (min-width: 960px) {
  .gerrit-layout {
    grid-template-columns: minmax(320px, 34%) minmax(0, 1fr);
    align-items: start;
    gap: 16px;
  }
}
@media (min-width: 1400px) {
  .gerrit-layout {
    grid-template-columns: minmax(380px, 30%) minmax(0, 1fr);
  }
}
@media (min-width: 1800px) {
  .gerrit-layout {
    grid-template-columns: minmax(420px, 26%) minmax(0, 1fr);
  }
}
.file-nav {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 10px;
  max-height: 82vh;
  overflow: auto;
  position: sticky;
  top: 12px;
}
.file-nav-title {
  padding: 10px 14px;
  font-weight: 600;
  border-bottom: 1px solid var(--border);
  background: #fafbfc;
  position: sticky;
  top: 0;
  z-index: 1;
}
.file-nav-item {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: flex-start;
  padding: 9px 14px;
  border-bottom: 1px solid #eef1f5;
  color: inherit !important;
  text-decoration: none !important;
  font-size: 12px;
}
.file-nav-item:hover { background: #f6f8fa; }
.file-nav-item .path {
  flex: 1;
  min-width: 0;
  overflow-wrap: anywhere;
  word-break: break-word;
  white-space: normal;
  line-height: 1.4;
  font-family: ui-monospace, Consolas, monospace;
}
.file-nav-item .stat {
  flex-shrink: 0;
  white-space: nowrap;
  padding-top: 1px;
}
.file-nav-item .add { color: #1a7f37; }
.file-nav-item .del { color: #cf222e; }
.commit-seg { border-top: 1px solid var(--border); }
.commit-seg-head {
  padding: 8px 10px;
  background: #f6f8fa;
  font-size: 12px;
  border-bottom: 1px solid #eef1f5;
}
.file-block {
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
  margin-bottom: 10px;
  background: #fff;
}
.file-path {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  padding: 9px 12px;
  background: #24292f;
  color: #f0f6fc;
  font-family: ui-monospace, Consolas, monospace;
  font-size: 12px;
  overflow-wrap: anywhere;
  word-break: break-word;
}
.file-stat {
  color: #8b949e;
  font-weight: normal;
  flex-shrink: 0;
  white-space: nowrap;
}
.diff-body {
  font-family: ui-monospace, Consolas, "Courier New", monospace;
  font-size: 12px;
  overflow-x: auto;
  background: #fff;
}
.diff-line {
  display: grid;
  grid-template-columns: 10px 1fr;
  white-space: pre;
  border-top: 1px solid #f0f0f0;
}
.diff-line code { padding: 0 8px; font-family: inherit; }
.diff-line.add { background: var(--add-bg); color: var(--add-fg); }
.diff-line.del { background: var(--del-bg); color: var(--del-fg); }
.diff-line.hunk { background: var(--hunk-bg); color: #0550ae; }
.diff-line.meta { background: var(--meta-bg); color: var(--muted); }
.gutter { border-right: 1px solid #eceff3; background: #fafafa; }
.banner, .trunc-note, .empty {
  padding: 10px 12px;
  background: #fff8c5;
  border: 1px solid #f2cc60;
  border-radius: 8px;
  margin-bottom: 10px;
  font-size: 13px;
}
.empty { background: #f6f8fa; border-color: var(--border); }
.btn {
  display: inline-block;
  padding: 4px 10px;
  border-radius: 6px;
  background: #0969da;
  color: #fff !important;
  text-decoration: none !important;
  font-size: 12px;
}
"""

