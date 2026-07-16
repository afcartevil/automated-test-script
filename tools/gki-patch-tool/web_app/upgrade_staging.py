"""Stage fix changes during upgrade; commit + push once per repo after successful build."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from web_app.upgrade_git import (
    commit,
    gerrit_browse_url_for_sha,
    has_staged_changes,
    head_sha,
    push,
    remote_get_url,
    repo_is_git,
    run_git,
    stage_all,
    stage_paths,
)


@dataclass
class CommitFinalizeResult:
    submissions: List[Dict[str, Any]]

    def summary_lines(self) -> List[str]:
        lines: List[str] = []
        for s in self.submissions:
            label = s.get("repo_label") or s.get("repo_key") or "仓库"
            sha = (s.get("commit_sha") or "")[:12]
            if sha:
                lines.append(f"{label}: {sha}")
            if s.get("pushed"):
                lines.append(f"{label}: 已 push ({s.get('push_cmd') or ''})")
            elif s.get("push_error"):
                lines.append(f"{label}: push 失败")
        return lines or [str(s.get("commit_sha") or "")[:12] for s in self.submissions if s.get("commit_sha")]


def persist_gerrit_submissions(job_id: str, entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Merge per-repo Gerrit submission records into job options."""
    from web_app.database import get_upgrade_job, update_upgrade_job

    job = get_upgrade_job(job_id) or {}
    opts = dict(job.get("options") or {})
    by_key: Dict[str, Dict[str, Any]] = {}
    for row in list(opts.get("gerrit_submissions") or []):
        if isinstance(row, dict) and row.get("repo_key"):
            by_key[str(row["repo_key"])] = dict(row)
    for row in entries:
        if not isinstance(row, dict):
            continue
        key = str(row.get("repo_key") or "").strip()
        if not key:
            continue
        old = by_key.get(key)
        if old is None:
            for existing_key, existing_row in list(by_key.items()):
                if _submission_keys_match(key, existing_key):
                    old = existing_row
                    key = existing_key
                    break
        by_key[key] = _merge_gerrit_submission_row(old, dict(row))
    merged = [_normalize_gerrit_submission_row(r) for r in by_key.values()]
    opts["gerrit_submissions"] = merged
    update_upgrade_job(job_id, options=opts)
    return merged


def _is_no_new_changes_error(err: str) -> bool:
    return "no new changes" in (err or "").lower()


def _submission_keys_match(a: str, b: str) -> bool:
    from web_app.target_repo_config import normalize_linux_path

    na = normalize_linux_path(str(a or "")).rstrip("/")
    nb = normalize_linux_path(str(b or "")).rstrip("/")
    if not na or not nb:
        return False
    if na == nb:
        return True
    if na.endswith(nb) or nb.endswith(na):
        return True
    ta = na.rsplit("/", 1)[-1]
    tb = nb.rsplit("/", 1)[-1]
    return bool(ta and ta == tb)


def _submission_on_gerrit(row: Dict[str, Any]) -> bool:
    if row.get("gerrit_url") or row.get("gerrit_urls"):
        return True
    if row.get("pushed"):
        return True
    if _is_no_new_changes_error(str(row.get("push_error") or "")):
        return True
    return False


def _fill_gerrit_url_from_meta(row: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(row)
    urls = list(out.get("gerrit_urls") or [])
    if not out.get("gerrit_url") and urls:
        out["gerrit_url"] = urls[0]
    return out


def _preserve_gerrit_meta(
    old: Optional[Dict[str, Any]],
    merged: Dict[str, Any],
) -> Dict[str, Any]:
    """Keep Gerrit link / branch from a prior successful push when retry overwrites with blanks."""
    if not old:
        return _fill_gerrit_url_from_meta(merged)
    out = dict(merged)
    for field in ("gerrit_url", "gerrit_urls", "push_cmd", "review_branch"):
        new_val = out.get(field)
        old_val = old.get(field)
        if field == "gerrit_urls":
            if not new_val and old_val:
                out[field] = list(old_val)
            continue
        if not new_val and old_val:
            out[field] = old_val
    return _fill_gerrit_url_from_meta(out)


def _repair_submission_gerrit_url(
    repo_root: Path,
    row: Dict[str, Any],
    *,
    remote: str = "origin",
) -> Dict[str, Any]:
    """Best-effort browse URL when push succeeded earlier but link was lost in a retry merge."""
    out = dict(row)
    if out.get("gerrit_url"):
        return out
    sha = (out.get("commit_sha") or "").strip()
    if not sha or not repo_is_git(repo_root):
        return out
    remote_url = remote_get_url(repo_root, remote)
    browse = gerrit_browse_url_for_sha(remote_url, sha)
    if browse:
        out["gerrit_url"] = browse
    return out


def _normalize_gerrit_submission_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Clear stale push_error when a repo is already on Gerrit."""
    out = _fill_gerrit_url_from_meta(dict(row))
    if _submission_on_gerrit(out):
        out["pushed"] = True
        out.pop("push_error", None)
    return out


def _merge_gerrit_submission_row(
    old: Optional[Dict[str, Any]],
    new: Dict[str, Any],
) -> Dict[str, Any]:
    if not old:
        return _preserve_gerrit_meta(None, dict(new))
    merged = dict(old)
    merged.update(new)
    err = str(merged.get("push_error") or "")
    if _is_no_new_changes_error(err):
        merged["pushed"] = True
        merged.pop("push_error", None)
        return _preserve_gerrit_meta(old, merged)
    if old.get("pushed") or old.get("gerrit_url") or old.get("gerrit_urls"):
        new_err = str(new.get("push_error") or "")
        if new_err and not new.get("pushed"):
            merged = dict(old)
            if new.get("commit_sha"):
                merged["commit_sha"] = new["commit_sha"]
            return _preserve_gerrit_meta(old, merged)
    return _preserve_gerrit_meta(old, merged)


def _find_submission(job: Dict[str, Any], norm_key: str) -> Optional[Dict[str, Any]]:
    for row in (job.get("options") or {}).get("gerrit_submissions") or []:
        if not isinstance(row, dict):
            continue
        key = str(row.get("repo_key") or "")
        if _submission_keys_match(key, norm_key):
            return dict(row)
    return None


def _pending_repo_already_on_gerrit(job: Dict[str, Any], norm_key: str) -> bool:
    row = _find_submission(job, norm_key)
    return bool(row and _submission_on_gerrit(row))


def _pending_repo_norm_key(repo_key: str) -> str:
    from web_app.target_repo_config import normalize_linux_path

    raw = str(repo_key or "").replace("\\", "/")
    if repo_is_git(Path(repo_key)):
        return _canonical_repo_key(Path(repo_key))
    return normalize_linux_path(raw).rstrip("/")


def _filter_pending_excluding_pushed(
    job: Dict[str, Any],
    pending: Dict[str, Any],
) -> Tuple[Dict[str, Any], List[str]]:
    """Drop repos that already succeeded Gerrit push in a prior attempt."""
    filtered: Dict[str, Any] = {}
    skipped: List[str] = []
    for repo_key, meta in pending.items():
        norm = _pending_repo_norm_key(repo_key)
        if _pending_repo_already_on_gerrit(job, norm):
            label = (meta or {}).get("label") or _repo_label(str(repo_key), job)
            skipped.append(label)
            continue
        filtered[repo_key] = meta
    return filtered, skipped


def _remove_repo_from_pending(job_id: str, norm_key: str) -> None:
    from web_app.database import get_upgrade_job
    from web_app.target_repo_config import normalize_linux_path

    job = get_upgrade_job(job_id) or {}
    pending = _load_pending(job)
    want = normalize_linux_path(norm_key).rstrip("/")
    for key in list(pending.keys()):
        if _pending_repo_norm_key(key) == want:
            pending.pop(key, None)
    _save_pending(job_id, pending)


def upgrade_target_repo_key(job: Dict[str, Any]) -> str:
    """Canonical Linux path of the upgrade target repo (not remote session ``.``)."""
    from web_app.target_repo_config import normalize_linux_path

    raw = (job.get("target_repo_dir") or "").strip()
    if raw:
        key = normalize_linux_path(raw).rstrip("/")
        if key and key != ".":
            return key
    repo_dir = Path(raw) if raw else Path(".")
    if repo_is_git(repo_dir):
        return _canonical_repo_key(repo_dir)
    return str(repo_dir).replace("\\", "/").rstrip("/")


def _canonical_repo_key(repo_root: Path) -> str:
    """Normalize to git toplevel so the same physical repo shares one pending key."""
    r = run_git(repo_root, ["rev-parse", "--show-toplevel"], check=False)
    if r.ok and (r.stdout or "").strip():
        return (r.stdout or "").strip().replace("\\", "/").rstrip("/")
    return str(repo_root).replace("\\", "/").rstrip("/")


def repo_matches_upgrade_target(job: Dict[str, Any], repo_key: str) -> bool:
    """Whether ``repo_key`` is the job's primary upgrade target repository."""
    from web_app.target_repo_config import normalize_linux_path

    target_key = upgrade_target_repo_key(job)
    norm_key = normalize_linux_path(str(repo_key).replace("\\", "/")).rstrip("/")
    if not target_key or target_key == ".":
        return True
    target_key = normalize_linux_path(target_key).rstrip("/")
    if norm_key == target_key:
        return True
    t_tail = target_key.rsplit("/", 1)[-1]
    n_tail = norm_key.rsplit("/", 1)[-1]
    if t_tail and t_tail == n_tail:
        return True
    return norm_key.endswith(target_key) or target_key.endswith(norm_key)


def gerrit_push_params_for_repo(
    job: Dict[str, Any],
    repo_key: str,
    *,
    saved_remote: str,
    saved_branch: str,
    meta: Optional[Dict[str, Any]] = None,
) -> Tuple[str, str]:
    """Gerrit push target: per-repo saved branch first, then upgrade target prepare-time branch."""
    entry = meta or {}
    per_branch = (entry.get("gerrit_review_branch") or "").strip()
    per_remote = (entry.get("gerrit_remote") or "").strip()
    if per_branch:
        return (per_remote or "origin").strip(), per_branch
    registry = _gerrit_saved_for_repo_root(job, repo_key)
    reg_branch = (registry.get("gerrit_review_branch") or "").strip()
    if reg_branch:
        return (registry.get("gerrit_remote") or "origin").strip(), reg_branch
    if saved_branch and repo_matches_upgrade_target(job, repo_key):
        return (saved_remote or "origin").strip(), saved_branch.strip()
    # Vendor/external repos in the same manifest often share the release branch.
    if saved_branch:
        return (saved_remote or "origin").strip(), saved_branch.strip()
    return "", ""


def gerrit_push_options_for_job(job: Dict[str, Any]) -> Dict[str, str]:
    opts = job.get("options") or {}
    return {
        "gerrit_remote": (opts.get("gerrit_remote") or "").strip(),
        "gerrit_review_branch": (opts.get("gerrit_review_branch") or "").strip(),
    }


def _gerrit_saved_for_repo_root(job: Dict[str, Any], repo_root: str) -> Dict[str, str]:
    from web_app.target_repo_config import normalize_linux_path

    root = normalize_linux_path(repo_root).rstrip("/")
    if not root:
        return {}
    registry = (job.get("options") or {}).get("repo_project_registry") or {}
    if isinstance(registry, dict):
        for info in registry.values():
            if not isinstance(info, dict):
                continue
            rr = normalize_linux_path((info.get("repo_root") or "")).rstrip("/")
            if rr == root and (info.get("gerrit_review_branch") or "").strip():
                return {
                    "gerrit_remote": (info.get("gerrit_remote") or "origin").strip(),
                    "gerrit_review_branch": (info.get("gerrit_review_branch") or "").strip(),
                }
    return {}


def ensure_gerrit_branch_captured_for_repo(
    job_id: str,
    job: Dict[str, Any],
    repo_root: str,
) -> Dict[str, str]:
    """On first build-fix touch: ``repo start local .`` + ``git status`` → save push branch."""
    from web_app.target_repo_config import normalize_linux_path
    from web_app.upgrade_git import capture_gerrit_review_branch
    from web_app.upgrade_service import _append_progress_log
    from web_app.build_fix_service import persist_repo_project_registry

    root = normalize_linux_path(repo_root).rstrip("/")
    if not root or not repo_is_git(Path(root)):
        return {}

    existing = _gerrit_saved_for_repo_root(job, root)
    if existing.get("gerrit_review_branch"):
        return existing

    try:
        gerrit_info = capture_gerrit_review_branch(Path(root))
    except Exception as exc:
        if job_id:
            _append_progress_log(
                job_id,
                f"Gerrit 分支解析失败（{root}）: {exc}",
                "build_fix",
            )
        return {}

    branch = (gerrit_info.get("gerrit_review_branch") or "").strip()
    remote = (gerrit_info.get("gerrit_remote") or "origin").strip()
    if not branch:
        if job_id:
            _append_progress_log(
                job_id,
                f"未能从 {root} 解析 Gerrit 分支（commit 时将重试 @{u}）",
                "build_fix",
            )
        return {}

    registry = dict((job.get("options") or {}).get("repo_project_registry") or {})
    merged = False
    for key, info in list(registry.items()):
        if not isinstance(info, dict):
            continue
        rr = normalize_linux_path((info.get("repo_root") or "")).rstrip("/")
        if rr == root or normalize_linux_path(str(key)).rstrip("/") == root:
            entry = dict(info)
            entry.update({
                "gerrit_remote": remote,
                "gerrit_review_branch": branch,
            })
            registry[key] = entry
            merged = True
    if not merged:
        registry[root] = {
            "repo_root": root,
            "gerrit_remote": remote,
            "gerrit_review_branch": branch,
        }
    if job_id:
        persist_repo_project_registry(job_id, registry)
        from web_app.database import get_upgrade_job

        fresh = get_upgrade_job(job_id) or job
        if isinstance(fresh.get("options"), dict):
            job["options"] = dict(fresh["options"])
        _append_progress_log(
            job_id,
            f"已保存 Gerrit 推送分支: {remote}/{branch}（{root}）",
            "build_fix",
        )
    return {"gerrit_remote": remote, "gerrit_review_branch": branch}


def _repo_label(repo_root: str, job: Dict[str, Any]) -> str:
    from web_app.build_fix_service import repo_display_name

    name = repo_display_name(job, repo_root)
    if name:
        return name
    root = (repo_root or "").replace("\\", "/").rstrip("/")
    target = (job.get("target_repo_dir") or "").replace("\\", "/").rstrip("/")
    build_wd = (job.get("build_workdir") or "").replace("\\", "/").rstrip("/")
    if target and (root == target or root.endswith(target) or target.endswith(root)):
        return "合入目标仓库"
    if build_wd and (root == build_wd or root.endswith(build_wd) or build_wd.endswith(root)):
        return "编译工作区"
    name = Path(root).name or root
    return name or "仓库"


def _collapse_pending_by_toplevel(
    pending: Dict[str, Any],
    job: Dict[str, Any],
) -> Dict[str, Any]:
    """Merge pending entries that belong to the same git repository."""
    collapsed: Dict[str, Any] = {}
    for repo_key, meta in pending.items():
        repo_root = Path(repo_key)
        top_key = _canonical_repo_key(repo_root) if repo_is_git(repo_root) else (
            str(repo_key).replace("\\", "/").rstrip("/")
        )
        entry = dict(collapsed.get(top_key) or {})
        label = entry.get("label") or meta.get("label") or _repo_label(top_key, job)
        paths = list(entry.get("paths") or [])
        for p in meta.get("paths") or []:
            if p and p not in paths:
                paths.append(p)
        build_fix_paths = list(entry.get("build_fix_paths") or [])
        for p in meta.get("build_fix_paths") or []:
            if p and p not in build_fix_paths:
                build_fix_paths.append(p)
        entry["label"] = label
        entry["paths"] = paths
        entry["build_fix_paths"] = build_fix_paths
        if meta.get("staged_all"):
            entry["staged_all"] = True
        if meta.get("commit_cwd"):
            entry["commit_cwd"] = meta["commit_cwd"]
        if meta.get("gerrit_remote"):
            entry["gerrit_remote"] = meta["gerrit_remote"]
        if meta.get("gerrit_review_branch"):
            entry["gerrit_review_branch"] = meta["gerrit_review_branch"]
        collapsed[top_key] = entry
    return collapsed


def git_toplevel_for_path(abs_path: str) -> Optional[Path]:
    from web_app.target_repo_config import normalize_linux_path
    from web_app.upgrade_remote_git import is_remote_active, remote_run_in_dir

    ap = normalize_linux_path((abs_path or "").strip().replace("\\", "/"))
    if not ap:
        return None
    parent = ap.rsplit("/", 1)[0] if "/" in ap else ap

    if is_remote_active():
        r = remote_run_in_dir(
            parent,
            "git rev-parse --show-toplevel 2>/dev/null",
            timeout=30,
        )
        top = (r.stdout or "").strip().replace("\\", "/").rstrip("/")
        return Path(top) if r.ok and top else None

    p = Path(ap)
    start = p if p.is_dir() else p.parent
    if not start.is_dir():
        return None
    r = run_git(start, ["rev-parse", "--show-toplevel"], check=False, capture_output=True)
    if not r.ok:
        return None
    top = (r.stdout or "").strip()
    return Path(top) if top else None


def resolve_remote_abs_for_job(
    job: Dict[str, Any],
    abs_path: str,
    build_workdir: str = "",
) -> str:
    """Map UNC / SMB / mistaken IP paths to the remote Linux path used for git."""
    from web_app.job_path_mapping import local_abs_to_remote
    from web_app.target_repo_config import normalize_linux_path

    raw = (abs_path or "").strip()
    if not raw:
        return ""

    if raw.startswith("\\\\") or (len(raw) >= 2 and raw[1] == ":" and raw[1] != "/"):
        remote = local_abs_to_remote(job, raw)
        if remote:
            return normalize_linux_path(remote).rstrip("/")

    ap = normalize_linux_path(raw.replace("\\", "/"))
    if re.match(r"^/\d+\.\d+\.\d+\.\d+/", ap):
        bw = normalize_linux_path((build_workdir or job.get("build_workdir") or "")).rstrip("/")
        target = normalize_linux_path((job.get("target_repo_dir") or "")).rstrip("/")
        vnd_root = bw or (target.rsplit("/kernel-5.10", 1)[0] if "/kernel-5.10" in (target or "") else target)
        for marker in ("vendor/mediatek", "vendor/", "kernel-5.10"):
            pos = ap.find(marker)
            if pos >= 0 and vnd_root:
                return normalize_linux_path(f"{vnd_root.rstrip('/')}/{ap[pos:]}").rstrip("/")
        if "gkiKernel/" in ap and vnd_root:
            suffix = ap.split("gkiKernel/", 1)[1]
            prefix = vnd_root.rsplit("/vnd", 1)[0] if vnd_root.endswith("/vnd") or "/vnd" in vnd_root else vnd_root.rsplit("/", 1)[0]
            return normalize_linux_path(f"{prefix}/gkiKernel/{suffix}").rstrip("/")

    return _normalize_abs_path_for_job(job, ap).rstrip("/")


def _normalize_abs_path_for_job(job: Dict[str, Any], abs_path: str) -> str:
    """Map UNC / mixed paths to Linux remote absolute paths when possible."""
    from web_app.target_repo_config import normalize_linux_path

    ap = normalize_linux_path((abs_path or "").strip())
    target = normalize_linux_path((job.get("target_repo_dir") or "").strip()).rstrip("/")
    build_wd = normalize_linux_path((job.get("build_workdir") or "")).rstrip("/")
    if not target and not build_wd:
        return ap
    if "kernel-5.10" in ap:
        ktail = ap.split("kernel-5.10", 1)[1].lstrip("/") if "kernel-5.10" in ap else ""
        if target and "kernel-5.10" in target:
            return f"{target}/{ktail}".rstrip("/") if ktail else target
        if build_wd and ktail:
            return f"{build_wd.rstrip('/')}/kernel-5.10/{ktail}".rstrip("/")
    if "vendor/mediatek" in ap or (ap.startswith("vendor/") and build_wd):
        idx = ap.find("vendor/")
        if idx >= 0:
            vnd_root = (
                target.rsplit("/kernel-5.10", 1)[0]
                if target and "/kernel-5.10" in target
                else build_wd or target
            )
            if vnd_root:
                return f"{vnd_root.rstrip('/')}/{ap[idx:].lstrip('/')}"
    return ap


def _rel_path_in_repo(repo_root: Path, abs_path: str, job: Dict[str, Any]) -> str:
    """Repo-relative path for ``git add``; avoids basename-only mistakes."""
    from web_app.target_repo_config import normalize_linux_path

    ap = _normalize_abs_path_for_job(job, abs_path)
    top_s = normalize_linux_path(_canonical_repo_key(repo_root)).rstrip("/")
    if top_s and ap.startswith(top_s + "/"):
        return ap[len(top_s) + 1 :]
    base = ap.rsplit("/", 1)[-1] if "/" in ap else ap
    if not base:
        return ""
    for args in (["diff", "--name-only", "HEAD"], ["diff", "--cached", "--name-only", "HEAD"]):
        r = run_git(repo_root, args, check=False)
        for line in (r.stdout or "").splitlines():
            s = line.strip().replace("\\", "/")
            if s == base or s.endswith("/" + base):
                return s
    r = run_git(repo_root, ["ls-files"], check=False)
    matches = []
    for line in (r.stdout or "").splitlines():
        s = line.strip().replace("\\", "/")
        if s == base or s.endswith("/" + base):
            matches.append(s)
    if len(matches) == 1:
        return matches[0]
    if matches:
        return matches[0]
    return ""


def resolve_repo_for_abs(
    job: Dict[str, Any],
    abs_path: str,
    *,
    build_workdir: str = "",
) -> Optional[Tuple[Path, str, str]]:
    """Return (repo_root, relpath_in_repo, repo_label) or None if not in a git repo."""
    from web_app.build_fix_service import repo_display_name
    from web_app.target_repo_config import normalize_linux_path
    from web_app.upgrade_service import _job_target_path, is_remote_job

    def label_for(root_s: str, fallback: str) -> str:
        return repo_display_name(job, root_s) or fallback

    ap = resolve_remote_abs_for_job(job, abs_path, build_workdir=build_workdir)
    if not ap:
        ap = _normalize_abs_path_for_job(job, abs_path)
    target_linux = normalize_linux_path((job.get("target_repo_dir") or "").strip()).rstrip("/")
    if is_remote_job(job) and target_linux and (ap == target_linux or ap.startswith(target_linux + "/")):
        rel = ap[len(target_linux) + 1 :] if ap.startswith(target_linux + "/") else "."
        return Path(target_linux), rel, label_for(target_linux, _repo_label(target_linux, job))

    target = _job_target_path(job)
    target_s = str(target).replace("\\", "/").rstrip("/")
    if target_s and target_s != "." and (ap == target_s or ap.startswith(target_s + "/")):
        rel = ap[len(target_s) + 1 :] if ap.startswith(target_s + "/") else "."
        if repo_is_git(target):
            return target, rel, label_for(target_s, _repo_label(target_s, job))

    top = git_toplevel_for_path(ap if ap.startswith("/") else abs_path)
    if top and repo_is_git(top):
        top_s = normalize_linux_path(_canonical_repo_key(top)).rstrip("/")
        rel = _rel_path_in_repo(top, ap, job)
        if not rel:
            return None
        return top, rel, label_for(top_s, _repo_label(top_s, job))

    if build_workdir:
        from web_app.build_fix_service import normalize_linux_path as norm_bw

        bw = norm_bw(build_workdir).rstrip("/")
        if bw and ap.startswith(bw + "/"):
            top = git_toplevel_for_path(ap)
            if top and repo_is_git(top):
                top_s = normalize_linux_path(_canonical_repo_key(top)).rstrip("/")
                rel = _rel_path_in_repo(top, ap, job)
                if rel:
                    return top, rel, label_for(top_s, _repo_label(top_s, job))
    return None


def _load_pending(job: Dict[str, Any]) -> Dict[str, Any]:
    opts = dict(job.get("options") or {})
    pending = dict(opts.get("pending_commit_repos") or {})
    return pending


def _save_pending(job_id: str, pending: Dict[str, Any]) -> None:
    from web_app.database import get_upgrade_job, update_upgrade_job

    job = get_upgrade_job(job_id) or {}
    opts = dict(job.get("options") or {})
    opts["pending_commit_repos"] = pending
    update_upgrade_job(job_id, options=opts)


def record_build_fix_for_commit(
    job_id: str,
    job: Dict[str, Any],
    abs_path: str,
    *,
    build_workdir: str = "",
) -> Optional[str]:
    """Record a build-fix file under its repo directory; commit happens after build succeeds."""
    from web_app.build_fix_service import (
        ensure_repo_project_captured_for_path,
        lookup_saved_repo_project,
        repo_display_name,
    )
    from web_app.database import get_upgrade_job
    from web_app.target_repo_config import normalize_linux_path
    from web_app.upgrade_service import _append_progress_log

    ap = resolve_remote_abs_for_job(job, abs_path, build_workdir=build_workdir)
    if not ap:
        return None

    if job_id:
        ensure_repo_project_captured_for_path(job_id, job, ap, build_workdir)
        job = get_upgrade_job(job_id) or job

    saved = lookup_saved_repo_project(job, ap)
    repo_root = normalize_linux_path((saved.get("repo_root") or "")).rstrip("/")

    if not repo_root:
        top = git_toplevel_for_path(ap)
        if top and repo_is_git(top):
            repo_root = normalize_linux_path(_canonical_repo_key(top)).rstrip("/")

    if not repo_root:
        target = normalize_linux_path((job.get("target_repo_dir") or "")).rstrip("/")
        if target and (ap == target or ap.startswith(target + "/")):
            repo_root = target

    if not repo_root:
        if job_id:
            _append_progress_log(
                job_id,
                f"编译修复: 无法解析提交目录（{ap}）",
                "build_fix",
            )
        return None

    rel = ""
    if ap.startswith(repo_root + "/"):
        rel = ap[len(repo_root) + 1 :]
    else:
        rel = _rel_path_in_repo(Path(repo_root), ap, job)

    if not rel or rel == ".":
        if job_id:
            _append_progress_log(
                job_id,
                f"编译修复: 无法解析仓库内相对路径（{ap} @ {repo_root}）",
                "build_fix",
            )
        return None

    gerrit_saved = ensure_gerrit_branch_captured_for_repo(job_id, job, repo_root)

    pending = _load_pending(job)
    key = _canonical_repo_key(Path(repo_root))
    entry = dict(pending.get(key) or {})
    label = repo_display_name(job, repo_root) or entry.get("label") or _repo_label(repo_root, job)
    entry["label"] = label
    entry["commit_cwd"] = repo_root
    if gerrit_saved.get("gerrit_review_branch"):
        entry["gerrit_remote"] = gerrit_saved.get("gerrit_remote") or "origin"
        entry["gerrit_review_branch"] = gerrit_saved["gerrit_review_branch"]
    bf_paths = list(entry.get("build_fix_paths") or [])
    if rel not in bf_paths:
        bf_paths.append(rel)
    entry["build_fix_paths"] = bf_paths
    pending[key] = entry
    _save_pending(job_id, pending)

    if job_id:
        _append_progress_log(
            job_id,
            f"已登记待提交: {label} ← {rel}（目录 {repo_root}）",
            "build_fix",
        )
    return key


def stage_path_for_job(
    job_id: str,
    job: Dict[str, Any],
    abs_path: str,
    *,
    build_workdir: str = "",
    from_build_fix: bool = False,
) -> Optional[str]:
    """Track a path for deferred commit.

    Build-fix writes only record repo + relative path; ``git add`` runs after build.
    Apply/conflict paths are staged immediately.
    """
    if from_build_fix:
        return record_build_fix_for_commit(
            job_id, job, abs_path, build_workdir=build_workdir,
        )

    resolved = resolve_repo_for_abs(job, abs_path, build_workdir=build_workdir)
    if not resolved:
        return None
    repo_root, rel, label = resolved
    if not rel or rel == ".":
        return None
    run_git(repo_root, ["add", "--", rel], check=False)
    pending = _load_pending(job)
    key = _canonical_repo_key(repo_root)
    entry = dict(pending.get(key) or {})
    entry["label"] = label
    entry["commit_cwd"] = str(repo_root).replace("\\", "/").rstrip("/")
    paths = list(entry.get("paths") or [])
    if rel not in paths:
        paths.append(rel)
    entry["paths"] = paths
    pending[key] = entry
    _save_pending(job_id, pending)
    return key


def stage_all_dirty_in_repo(job_id: str, job: Dict[str, Any], repo_root: Path) -> None:
    """Stage all current merge/apply changes before build (pre-compile; not used at final commit)."""
    if not repo_is_git(repo_root):
        return
    stage_all(repo_root)
    key = _canonical_repo_key(repo_root)
    pending = _load_pending(job)
    status = run_git(repo_root, ["status", "--porcelain"], check=False).stdout or ""
    paths = []
    for line in status.splitlines():
        if len(line) >= 4:
            paths.append(line[3:].strip())
    if paths:
        pending[key] = {"label": _repo_label(key, job), "paths": paths, "staged_all": True}
        _save_pending(job_id, pending)


def stage_apply_changes_for_job(job_id: str, job: Dict[str, Any]) -> int:
    """After apply/conflict resolution: ``git add -A`` on target repo and record paths for later commit."""
    from web_app.upgrade_git import is_clean_worktree
    from web_app.upgrade_service import _job_target_path

    target = _job_target_path(job)
    if is_clean_worktree(target):
        return 0
    stage_all_dirty_in_repo(job_id, job, target)
    return len((_load_pending(job).get(_canonical_repo_key(target)) or {}).get("paths") or [])


def _porcelain_path_from_line(line: str) -> str:
    """Extract a repo-relative path from ``git status --porcelain`` line.

    Standard format is ``XY<space><path>`` (path starts at index 3). Some
    worktrees (notably GPU symlink trees) occasionally emit ``XY<path>`` with
    no separator space; slicing at index 3 then turns ``gpu_mali/...`` into
    the bogus ``pu_mali/...``.
    """
    line = line.rstrip("\n\r")
    if len(line) < 3:
        return ""
    if len(line) >= 4 and line[2] == " ":
        raw = line[3:].strip()
    else:
        raw = line[2:].strip()
    if not raw:
        return ""
    if raw.startswith('"') and raw.endswith('"'):
        try:
            raw = bytes(raw[1:-1], "utf-8").decode("unicode_escape")
        except Exception:
            raw = raw[1:-1]
    if " -> " in raw:
        return raw.split(" -> ", 1)[0].strip()
    return raw


def _stage_paths_via_porcelain(repo_root: Path, wanted: List[str]) -> None:
    """Fallback when ``git add path`` fails (e.g. path crosses a symlink in the worktree)."""
    import posixpath

    want_set = {posixpath.normpath((p or "").strip()) for p in wanted if (p or "").strip()}
    want_names = {posixpath.basename(p) for p in want_set}
    r = run_git(repo_root, ["status", "--porcelain", "-u"], check=False)
    if not r.ok:
        return
    to_add: List[str] = []
    for line in (r.stdout or "").splitlines():
        if len(line) < 4:
            continue
        path = _porcelain_path_from_line(line)
        if not path:
            continue
        norm = posixpath.normpath(path)
        if norm in want_set or posixpath.basename(norm) in want_names:
            to_add.append(path)
    if to_add:
        _stage_paths_one_by_one(repo_root, to_add)


def _stage_paths_one_by_one(repo_root: Path, paths: List[str]) -> None:
    for path in paths:
        if path:
            run_git(repo_root, ["add", "--", path], check=False)


def _stage_all_tracked_dirty(repo_root: Path) -> None:
    """``git add -u`` — stage all tracked modifications (symlink-safe fallback)."""
    run_git(repo_root, ["add", "-u"], check=False)


def _stage_unstaged_worktree_changes(repo_root: Path) -> List[str]:
    """Stage modified/added paths still dirty after explicit pathspec add (build-fix safety net)."""
    r = run_git(repo_root, ["status", "--porcelain", "-u"], check=False)
    if not r.ok:
        return []
    to_add: List[str] = []
    for line in (r.stdout or "").splitlines():
        if len(line) < 4:
            continue
        xy = line[:2]
        if not any(ch in xy for ch in "MADRCU?"):
            continue
        path = _porcelain_path_from_line(line)
        if path:
            to_add.append(path)
    if to_add:
        _stage_paths_one_by_one(repo_root, to_add)
        if not has_staged_changes(repo_root):
            _stage_all_tracked_dirty(repo_root)
    return to_add


def _basename_set(paths: List[str]) -> set[str]:
    import posixpath

    return {posixpath.basename((p or "").strip()) for p in paths if (p or "").strip()}


def _cached_staged_basenames(repo_root: Path) -> set[str]:
    import posixpath

    r = run_git(repo_root, ["diff", "--cached", "--name-only"], check=False)
    if not r.ok:
        return set()
    return {posixpath.basename(p.strip()) for p in (r.stdout or "").splitlines() if p.strip()}


def _modified_tracked_paths(
    repo_root: Path,
    *,
    basenames: Optional[set[str]] = None,
) -> List[str]:
    import posixpath

    r = run_git(repo_root, ["ls-files", "-m"], check=False)
    if not r.ok:
        return []
    paths = [p.strip() for p in (r.stdout or "").splitlines() if p.strip()]
    if basenames:
        paths = [p for p in paths if posixpath.basename(p) in basenames]
    return paths


def _stage_modified_tracked_files(
    repo_root: Path,
    *,
    basenames: Optional[set[str]] = None,
) -> List[str]:
    paths = _modified_tracked_paths(repo_root, basenames=basenames)
    if paths:
        _stage_paths_one_by_one(repo_root, paths)
    return paths


def _ensure_wanted_basenames_staged(
    repo_root: Path,
    wanted_paths: List[str],
    *,
    job_id: str = "",
    label: str = "",
) -> None:
    """Stage build-fix files by basename using ``git ls-files -m`` (symlink-safe)."""
    from web_app.upgrade_service import _append_progress_log

    want = _basename_set(wanted_paths)
    if not want:
        return
    staged = _cached_staged_basenames(repo_root)
    missing = want - staged
    if not missing:
        return
    added = _stage_modified_tracked_files(repo_root, basenames=missing)
    staged = _cached_staged_basenames(repo_root)
    still_missing = want - staged
    if still_missing:
        _stage_all_tracked_dirty(repo_root)
        staged = _cached_staged_basenames(repo_root)
        still_missing = want - staged
    if added and job_id:
        _append_progress_log(
            job_id,
            f"{label or repo_root}: git ls-files 补充暂存 {len(added)} 个路径 "
            f"({', '.join(added[:3])}{'…' if len(added) > 3 else ''})",
            "commit",
        )
    if still_missing and job_id:
        _append_progress_log(
            job_id,
            f"{label or repo_root}: 警告: 仍有 {len(still_missing)} 个文件未暂存 "
            f"({', '.join(sorted(still_missing)[:4])})",
            "commit",
        )


def _restage_pending_paths(
    repo_root: Path,
    meta: Dict[str, Any],
    *,
    job_id: str = "",
    label: str = "",
) -> None:
    """Re-stage paths before commit.

    If apply/conflict already ran ``git add -A`` (``staged_all``), only stage
    files touched during build-fix. Otherwise stage all recorded build-fix paths.

    Build-fix paths under symlink trees (e.g. GPU ``mt6789/...``) cannot be
    passed to ``git add`` directly; use ``git ls-files -m`` + basename match.
    """
    bf = list(meta.get("build_fix_paths") or [])
    apply_paths = [] if bf else list(meta.get("paths") or [])

    if bf:
        _ensure_wanted_basenames_staged(
            repo_root, bf, job_id=job_id, label=label,
        )
    if apply_paths:
        stage_paths(repo_root, apply_paths)
        if not has_staged_changes(repo_root):
            _stage_paths_via_porcelain(repo_root, apply_paths)
        if not has_staged_changes(repo_root):
            _stage_all_tracked_dirty(repo_root)


def finalize_deferred_commits(
    job_id: str,
    job: Dict[str, Any],
    *,
    message: Optional[str] = None,
    message_file: str = "",
    push_remote: bool = True,
) -> CommitFinalizeResult:
    """Create one commit per repo with staged fixes, then push."""
    from web_app.database import get_upgrade_job
    from web_app.upgrade_service import _append_progress_log, _set_progress, resolve_git_commit_message

    job = get_upgrade_job(job_id) or dict(job)
    pending = _collapse_pending_by_toplevel(_load_pending(job), job)
    pending, skipped_labels = _filter_pending_excluding_pushed(job, pending)
    for label in skipped_labels:
        _append_progress_log(job_id, f"{label}: 已于前次提交 push，跳过", "commit")
    if skipped_labels:
        _save_pending(job_id, pending)

    if not pending:
        existing_subs = [
            _normalize_gerrit_submission_row(dict(row))
            for row in (job.get("options") or {}).get("gerrit_submissions") or []
            if isinstance(row, dict) and _submission_on_gerrit(row)
        ]
        if existing_subs:
            _append_progress_log(job_id, "所有待提交仓库均已成功 push", "commit")
            _save_pending(job_id, {})
            repaired: List[Dict[str, Any]] = []
            for row in existing_subs:
                repo_root = Path(str(row.get("repo_root") or row.get("repo_key") or ""))
                repaired.append(
                    _normalize_gerrit_submission_row(
                        _repair_submission_gerrit_url(repo_root, row)
                        if repo_is_git(repo_root)
                        else row,
                    ),
                )
            merged = persist_gerrit_submissions(job_id, repaired)
            _set_progress(job_id, {"gerrit_submissions": merged, "skip_log": True})
            return CommitFinalizeResult(submissions=merged)

    gerrit_opts = gerrit_push_options_for_job(job)
    saved_gerrit_remote = gerrit_opts["gerrit_remote"]
    saved_gerrit_branch = gerrit_opts["gerrit_review_branch"]

    if not pending:
        target_key = upgrade_target_repo_key(job)
        if target_key and repo_is_git(Path(target_key)):
            pending = {
                target_key: {
                    "label": _repo_label(target_key, job),
                    "paths": [],
                    "push_only": True,
                },
            }
        else:
            from web_app.upgrade_service import _job_target_path

            target = _job_target_path(job)
            if repo_is_git(target):
                key = _canonical_repo_key(target)
                pending = {
                    key: {
                        "label": _repo_label(key, job),
                        "paths": [],
                        "push_only": True,
                    },
                }

    if message is None and not message_file:
        message, message_file, _preview = resolve_git_commit_message(job)
    elif not message:
        message = ""

    submissions: List[Dict[str, Any]] = []

    for repo_key, meta in pending.items():
        repo_root = Path(repo_key)
        if not repo_is_git(repo_root):
            continue
        label = meta.get("label") or _repo_label(repo_key, job)
        norm_key = _canonical_repo_key(repo_root)
        job = get_upgrade_job(job_id) or job
        if push_remote and _pending_repo_already_on_gerrit(job, norm_key):
            prior = _find_submission(job, norm_key)
            if prior:
                row = _normalize_gerrit_submission_row(
                    _repair_submission_gerrit_url(repo_root, dict(prior)),
                )
                submissions.append(row)
                _append_progress_log(
                    job_id,
                    f"{label}: 已在 Gerrit（保留已有链接），跳过",
                    "commit",
                )
                _remove_repo_from_pending(job_id, norm_key)
                merged = persist_gerrit_submissions(job_id, [row])
                _set_progress(job_id, {"gerrit_submissions": merged, "skip_log": True})
                continue
        commit_cwd = (meta.get("commit_cwd") or norm_key or "").strip()
        bf = list(meta.get("build_fix_paths") or [])
        if meta.get("staged_all"):
            if bf:
                _append_progress_log(
                    job_id,
                    f"{label}: 进入 {commit_cwd or norm_key}，编译修复 git add {len(bf)} 个路径",
                    "commit",
                )
            else:
                _append_progress_log(
                    job_id,
                    f"{label}: 合入阶段已 git add，无编译修复增量路径",
                    "commit",
                )
        elif bf:
            _append_progress_log(
                job_id,
                f"{label}: 进入 {commit_cwd or norm_key}，编译修复 git add {len(bf)} 个路径",
                "commit",
            )
        elif meta.get("paths"):
            _append_progress_log(
                job_id,
                f"{label}: 进入 {commit_cwd or norm_key}，git add {len(meta.get('paths') or [])} 个路径",
                "commit",
            )
        _restage_pending_paths(repo_root, meta, job_id=job_id, label=label)

        sha = ""
        did_commit = False
        if has_staged_changes(repo_root):
            sha = commit(repo_root, message or "", message_file=message_file)
            did_commit = True
            _append_progress_log(job_id, f"{label}: commit {sha[:12]}", "commit")
        elif push_remote:
            sha = head_sha(repo_root)
            if sha:
                _append_progress_log(
                    job_id,
                    f"{label}: 无新暂存变更，推送已有 commit {sha[:12]}",
                    "commit",
                )
        if not sha:
            _append_progress_log(job_id, f"{label}: 无可提交/推送的变更，已跳过", "commit")
            continue

        prior = _find_submission(job, norm_key)
        entry: Dict[str, Any] = {
            "repo_key": norm_key,
            "repo_label": label,
            "repo_root": norm_key,
            "commit_sha": sha,
            "pushed": False,
            "push_cmd": (prior or {}).get("push_cmd") or "",
            "review_branch": (prior or {}).get("review_branch") or "",
            "gerrit_url": (prior or {}).get("gerrit_url") or "",
            "gerrit_urls": list((prior or {}).get("gerrit_urls") or []),
            "paths": list(meta.get("paths") or []),
            "build_fix_paths": list(meta.get("build_fix_paths") or []),
            "did_commit": did_commit,
        }
        if push_remote:
            captured = ensure_gerrit_branch_captured_for_repo(job_id, job, norm_key)
            if captured.get("gerrit_review_branch"):
                meta = dict(meta)
                meta["gerrit_remote"] = captured.get("gerrit_remote") or "origin"
                meta["gerrit_review_branch"] = captured["gerrit_review_branch"]
            job = get_upgrade_job(job_id) or job
            gerrit_remote, gerrit_branch = gerrit_push_params_for_repo(
                job,
                norm_key,
                saved_remote=saved_gerrit_remote,
                saved_branch=saved_gerrit_branch,
                meta=meta,
            )
            if gerrit_branch:
                _append_progress_log(
                    job_id,
                    f"使用已保存的 Gerrit 分支 push: "
                    f"{gerrit_remote or 'origin'}/{gerrit_branch}",
                    "commit",
                )
            try:
                push_result = push(
                    repo_root,
                    gerrit_remote=gerrit_remote,
                    gerrit_review_branch=gerrit_branch,
                )
                entry["pushed"] = True
                entry["push_cmd"] = push_result.cmd
                entry["review_branch"] = push_result.review_branch
                entry["gerrit_urls"] = list(push_result.gerrit_urls)
                if push_result.gerrit_urls:
                    entry["gerrit_url"] = push_result.gerrit_urls[0]
                else:
                    remote_url = remote_get_url(repo_root, push_result.remote or "origin")
                    entry["gerrit_url"] = gerrit_browse_url_for_sha(remote_url, sha)
                _append_progress_log(
                    job_id,
                    f"{label}: 已 push Gerrit ({push_result.cmd})",
                    "commit",
                )
            except Exception as exc:
                err = str(exc).strip() or "push 失败"
                if _is_no_new_changes_error(err):
                    refreshed = get_upgrade_job(job_id) or job
                    prior = _find_submission(refreshed, norm_key)
                    skip_entry = dict(prior) if prior else dict(entry)
                    skip_entry.update({
                        "repo_key": norm_key,
                        "repo_label": label,
                        "repo_root": norm_key,
                        "commit_sha": sha or skip_entry.get("commit_sha") or "",
                        "pushed": True,
                    })
                    if not skip_entry.get("review_branch") and saved_gerrit_branch:
                        skip_entry["review_branch"] = saved_gerrit_branch
                    skip_entry.pop("push_error", None)
                    skip_entry = _preserve_gerrit_meta(prior, skip_entry)
                    skip_entry = _repair_submission_gerrit_url(
                        repo_root,
                        skip_entry,
                        remote=gerrit_remote or "origin",
                    )
                    _append_progress_log(
                        job_id,
                        f"{label}: Gerrit 无新变更（已提交过），跳过",
                        "commit",
                    )
                    submissions.append(skip_entry)
                    persist_gerrit_submissions(job_id, submissions)
                    _remove_repo_from_pending(job_id, norm_key)
                    continue
                entry["push_error"] = err
                _append_progress_log(job_id, f"{label}: push 失败: {entry['push_error']}", "commit")
                submissions.append(entry)
                merged = persist_gerrit_submissions(job_id, submissions)
                _set_progress(job_id, {"gerrit_submissions": merged, "skip_log": True})
                raise
        submissions.append(entry)
        if entry.get("pushed"):
            _remove_repo_from_pending(job_id, norm_key)
            merged = persist_gerrit_submissions(job_id, [entry])
            _set_progress(job_id, {"gerrit_submissions": merged, "skip_log": True})

    _save_pending(job_id, _load_pending(get_upgrade_job(job_id) or job))
    if not submissions:
        raise RuntimeError(
            "未产生任何 commit 或 Gerrit push。"
            "若此前已 commit 但 push 失败，请确认 prepare 阶段已保存 Gerrit 分支后重试。"
        )
    if push_remote and not any(s.get("pushed") for s in submissions):
        raise RuntimeError("commit 已完成但 Gerrit push 未成功，请查看日志后重试提交")
    if submissions:
        merged = persist_gerrit_submissions(job_id, submissions)
        _set_progress(job_id, {"gerrit_submissions": merged, "skip_log": True})
        return CommitFinalizeResult(submissions=merged)
    return CommitFinalizeResult(submissions=[])
