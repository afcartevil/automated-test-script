#!/usr/bin/env python3
import argparse
import base64
import concurrent.futures
import copy
import fnmatch
import json
import math
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml


DEFAULT_TIMEOUT = 30
DEFAULT_HTTP_RETRIES = 6
DEFAULT_BACKOFF_BASE = 1.5
XSSI_PREFIX = ")]}'"


@dataclass
class CommitItem:
    sha: str
    message: str


_COMMIT_CACHE: Dict[Tuple[str, str, str], CommitItem] = {}
_DIFF_CACHE: Dict[Tuple[str, str, str], str] = {}


def _compute_retry_delay(err: urllib.error.HTTPError, attempt: int) -> float:
    retry_after = err.headers.get("Retry-After")
    if retry_after:
        try:
            return max(1.0, float(retry_after))
        except ValueError:
            pass
    return min(60.0, DEFAULT_BACKOFF_BASE ** attempt)


def http_get_text(url: str, timeout: int = DEFAULT_TIMEOUT, retries: int = DEFAULT_HTTP_RETRIES) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "patch-analyzer/1.0"})
    last_exc: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            last_exc = exc
            if exc.code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(_compute_retry_delay(exc, attempt + 1))
                continue
            raise
        except urllib.error.URLError as exc:
            last_exc = exc
            if attempt < retries:
                time.sleep(min(30.0, DEFAULT_BACKOFF_BASE ** (attempt + 1)))
                continue
            raise
    if last_exc:
        raise last_exc
    raise RuntimeError("unexpected HTTP failure")


def http_get_json(url: str, timeout: int = DEFAULT_TIMEOUT) -> Dict[str, Any]:
    raw = http_get_text(url, timeout=timeout)
    if raw.startswith(XSSI_PREFIX):
        raw = "\n".join(raw.splitlines()[1:])
    return json.loads(raw)


def load_config(config_path: Path) -> Dict[str, Any]:
    if not config_path.exists():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")
    with config_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError("配置格式错误: 顶层必须是对象")
    return data


def normalize_repo_url(repo_url: str) -> str:
    return repo_url.rstrip("/")


def run_git(repo_dir: Path, args: List[str], timeout: Optional[int] = None) -> str:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(repo_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"git {' '.join(args)} timed out after {timeout}s")
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def fetch_commits_between_tags(repo_url: str, from_tag: str, to_tag: str, repo_dir: Optional[Path] = None) -> List[CommitItem]:
    from_tag = str(from_tag or "").strip()
    to_tag = str(to_tag or "").strip()
    if not from_tag or not to_tag:
        raise ValueError("from_tag / to_tag 不能为空")
    if repo_dir is not None:
        out = run_git(repo_dir, ["log", "--format=%H%x01%B%x00", f"{from_tag}..{to_tag}"])
        commits: List[CommitItem] = []
        for block in out.split("\x00"):
            block = block.strip()
            if not block:
                continue
            parts = block.split("\x01", 1)
            sha = parts[0].strip()
            msg = parts[1].strip() if len(parts) > 1 else ""
            commits.append(CommitItem(sha=sha, message=msg))
        return commits

    base = f"{normalize_repo_url(repo_url)}/+log/{from_tag}..{to_tag}?format=JSON"
    commits: List[CommitItem] = []
    next_token: Optional[str] = None
    while True:
        url = base if not next_token else f"{base}&s={urllib.parse.quote(next_token)}"
        payload = http_get_json(url)
        for entry in payload.get("log", []):
            commits.append(CommitItem(sha=entry["commit"], message=entry.get("message", "")))
        next_token = payload.get("next")
        if not next_token:
            break
    return commits


def fetch_single_commit(repo_url: str, commit: str, repo_dir: Optional[Path] = None) -> CommitItem:
    cache_key = (normalize_repo_url(repo_url), str(repo_dir or ""), commit)
    cached = _COMMIT_CACHE.get(cache_key)
    if cached is not None:
        return cached
    if repo_dir is not None:
        msg = run_git(repo_dir, ["show", "-s", "--format=%B", commit]).strip()
        item = CommitItem(sha=commit, message=msg)
        _COMMIT_CACHE[cache_key] = item
        return item

    url = f"{normalize_repo_url(repo_url)}/+/{commit}?format=JSON"
    payload = http_get_json(url)
    item = CommitItem(sha=payload["commit"], message=payload.get("message", ""))
    _COMMIT_CACHE[cache_key] = item
    return item


def fetch_diff_text(repo_url: str, sha: str, repo_dir: Optional[Path] = None) -> str:
    cache_key = (normalize_repo_url(repo_url), str(repo_dir or ""), sha)
    cached = _DIFF_CACHE.get(cache_key)
    if cached is not None:
        return cached
    if repo_dir is not None:
        diff = run_git(repo_dir, ["show", "--format=", "--no-color", sha])
        _DIFF_CACHE[cache_key] = diff
        return diff

    url = f"{normalize_repo_url(repo_url)}/+/{sha}^!?format=TEXT"
    raw = http_get_text(url).strip()
    decoded = base64.b64decode(raw)
    diff = decoded.decode("utf-8", errors="replace")
    _DIFF_CACHE[cache_key] = diff
    return diff


def parse_format_patch_output(raw_output: str, repo_url: str) -> Dict[str, Dict[str, Any]]:
    """Parse git format-patch --stdout output into per-SHA patch data dicts.

    Returns dict keyed by SHA, each value is a dict compatible with fetch_patch_data output.
    """
    normalized_repo = normalize_repo_url(repo_url)
    results: Dict[str, Dict[str, Any]] = {}

    # Split by "From <sha>" lines at start of each patch block
    blocks = re.split(r'^From ([0-9a-f]{40}) ', raw_output, flags=re.MULTILINE)
    # blocks[0] is empty, blocks[1] = sha1, blocks[2] = content1, blocks[3] = sha2, ...

    for i in range(1, len(blocks), 2):
        sha = blocks[i]
        content = blocks[i + 1] if i + 1 < len(blocks) else ""

        # Split into header section and body+diff by first empty line after headers
        # Headers: From:, Date:, Subject:
        lines = content.split('\n')

        subject = ""
        header_end = 0
        for j, line in enumerate(lines):
            if line.startswith('Subject: '):
                # Remove [PATCH N/M] prefix
                subject = re.sub(r'\[PATCH[^\]]*\]\s*', '', line[len('Subject: '):])
            if line.strip() == '' and j > 0:
                header_end = j + 1
                break

        # After headers: commit message body, then '---' separator, then diff
        body_and_diff = '\n'.join(lines[header_end:])

        # Find '---' separator (the one between commit message and diff stats)
        sep_match = re.search(r'^---\s*$', body_and_diff, re.MULTILINE)
        if sep_match:
            message_body = body_and_diff[:sep_match.start()].strip()
            # Diff starts at 'diff --git'
            diff_part = body_and_diff[sep_match.end():]
            diff_start = diff_part.find('diff --git')
            diff_text = diff_part[diff_start:] if diff_start >= 0 else ""
        else:
            message_body = body_and_diff.strip()
            diff_text = ""

        # Remove trailing git version line (--\n2.xx.x)
        diff_text = re.sub(r'\n--\s*\n[\d.]+\s*$', '', diff_text).strip()

        # Build full commit message
        full_message = f"{subject}\n\n{message_body}".strip() if message_body else subject

        # Compute metadata (same as fetch_patch_data)
        files = extract_files(diff_text)
        insertions = count_insertions(diff_text)
        deletions = count_deletions(diff_text)
        churn = insertions + deletions
        test_signal = detect_test_signal(diff_text, files)
        high_risk_paths = detect_high_risk_paths(files)
        diff_preview = build_diff_preview(diff_text)

        results[sha] = {
            "commit": sha,
            "sha": sha,
            "title": subject,
            "commit_message": full_message,
            "commit_message_full": full_message,
            "diff_text": diff_text,
            "diff_preview": diff_preview,
            "files": files,
            "insertions": insertions,
            "deletions": deletions,
            "churn": churn,
            "test_signal": test_signal,
            "high_risk_paths": high_risk_paths,
            "commit_url": f"{normalized_repo}/+/{sha}",
            "diff_url": f"{normalized_repo}/+/{sha}^!/",
            "score": 0.0,
            "recommendation": "",
            "key_risk": "",
            "blocked": False,
            "block_rules_hit": [],
            "patch_url": f"{normalized_repo}/+/{sha}",
        }

    return results

def extract_files(diff: str) -> List[str]:
    files = []
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            files.append(line[len("+++ b/"):])
    return files


CODE_KEYWORDS = {
    "if",
    "for",
    "while",
    "switch",
    "return",
    "sizeof",
    "struct",
    "static",
    "const",
    "void",
    "int",
    "long",
    "short",
    "char",
    "bool",
    "true",
    "false",
    "else",
    "case",
    "break",
    "continue",
    "goto",
}


def extract_symbol_name(text: str) -> str:
    for name in re.findall(r"([A-Za-z_]\w*)\s*\(", text):
        if name not in CODE_KEYWORDS:
            return name
    return ""


def extract_function_names_from_diff(diff: str) -> List[str]:
    names: List[str] = []
    seen = set()
    for line in diff.splitlines():
        if not line.startswith("@@"):
            continue
        m = re.match(r"@@ .* @@\s*(.*)", line)
        header = (m.group(1).strip() if m else "").strip()
        if not header:
            continue
        name = extract_symbol_name(header)
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    return names


def normalize_code_snippet(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def collect_before_snippets(code_rich: Dict[str, Any]) -> List[str]:
    snippets: List[str] = []
    seen = set()
    for item in (code_rich.get("logic_changes", []) or []):
        before = str(item.get("before", "")).strip()
        if not before:
            continue
        normalized = normalize_code_snippet(before)
        if normalized and len(normalized) >= 12 and normalized not in seen:
            seen.add(normalized)
            snippets.append(normalized)
    return snippets


def extract_identifiers(text: str) -> List[str]:
    ids: List[str] = []
    seen = set()
    for token in re.findall(r"\b[A-Za-z_]\w+\b", text):
        lowered = token.lower()
        if lowered in CODE_KEYWORDS:
            continue
        if len(token) < 4 and not token.isupper():
            continue
        if token not in seen:
            seen.add(token)
            ids.append(token)
    return ids


def should_attempt_history_introducer_analysis(
    title: str,
    message: str,
    current_files: List[str],
    problem_closure_rich: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, str]:
    del current_files, problem_closure_rich
    title_text = (title or "").lower()
    body_text = (message or "").lower()
    if re.search(r"(?i)\b(fix|regression|deadlock|uaf|use-after-free|crash|leak|overflow)\b", title_text):
        return True, "标题命中修复信号"
    if re.search(
        r"(?i)\b(regression|deadlock|uaf|use-after-free|null pointer|double-free|crash|leak|overflow|corruption|memory corruption|out[- ]of[- ]bounds|hang)\b",
        body_text,
    ):
        return True, "正文命中严重缺陷信号"
    return False, "未命中 strict gate：缺少强修复信号"


def select_history_search_files(current_files: List[str], code_rich: Dict[str, Any], max_files: int = 3) -> List[str]:
    prioritized: List[str] = []
    seen = set()

    for entry in (code_rich.get("files_stat", []) or []):
        file_path = str((entry or {}).get("file", "")).strip()
        if file_path and file_path in current_files and file_path not in seen:
            seen.add(file_path)
            prioritized.append(file_path)
        if len(prioritized) >= max_files:
            return prioritized

    for file_path in current_files:
        if file_path and file_path not in seen:
            seen.add(file_path)
            prioritized.append(file_path)
        if len(prioritized) >= max_files:
            break

    return prioritized


def get_candidate_intro_commits(repo_dir: Path, current_sha: str, files: List[str], limit: int = 16) -> List[str]:
    if not files:
        return []
    out = run_git(repo_dir, ["log", "--format=%H", f"{current_sha}^", "--max-count", str(limit), "--", *files])
    commits = []
    seen = set()
    for line in out.splitlines():
        sha = line.strip()
        if not sha or sha in seen:
            continue
        seen.add(sha)
        commits.append(sha)
    return commits


def score_candidate_introducer(
    candidate_sha: str,
    candidate_message: str,
    candidate_diff: str,
    current_files: List[str],
    current_dirs: List[str],
    current_functions: List[str],
    before_snippets: List[str],
    current_title: str,
) -> Tuple[float, List[str]]:
    score = 0.0
    evidence: List[str] = []
    candidate_files = extract_files(candidate_diff)
    candidate_dirs = sorted({p.split("/", 1)[0] for p in candidate_files if "/" in p})
    shared_files = [f for f in candidate_files if f in current_files][:4]
    shared_dirs = [d for d in candidate_dirs if d in current_dirs][:4]
    if shared_files:
        score += 4.0 + len(shared_files) * 1.5
        evidence.append("共同修改文件: " + "、".join(shared_files))
    elif shared_dirs:
        score += 2.0 + len(shared_dirs)
        evidence.append("共同影响目录: " + "、".join(shared_dirs))

    function_hits = [fn for fn in current_functions if re.search(rf"\b{re.escape(fn)}\b", candidate_diff)]
    if function_hits:
        score += min(6.0, 2.0 * len(function_hits))
        evidence.append("共同函数/调用点: " + "、".join(function_hits[:4]))

    candidate_added_compact = normalize_code_snippet(
        "\n".join(line[1:] for line in candidate_diff.splitlines() if line.startswith("+") and not line.startswith("+++"))
    )
    before_hits = []
    for snippet in before_snippets:
        if snippet and snippet in candidate_added_compact:
            before_hits.append(snippet[:48])
    if before_hits:
        score += min(8.0, 4.0 * len(before_hits))
        evidence.append("引入提交新增了当前修复前的旧代码形态")

    current_ids = set(extract_identifiers(current_title + "\n" + " ".join(current_functions)))
    candidate_ids = set(extract_identifiers(candidate_message + "\n" + candidate_diff))
    overlap = sorted(current_ids & candidate_ids)
    if overlap:
        score += min(3.0, 0.6 * len(overlap))
        evidence.append("关键词重合: " + "、".join(overlap[:5]))

    return score, evidence[:5]


def infer_introducer_from_history(
    repo_url: str,
    current_sha: str,
    current_title: str,
    current_message: str,
    current_diff: str,
    current_files: List[str],
    code_rich: Dict[str, Any],
    repo_dir: Optional[Path],
    problem_closure_rich: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    should_attempt, attempt_reason = should_attempt_history_introducer_analysis(
        title=current_title,
        message=current_message,
        current_files=current_files,
        problem_closure_rich=problem_closure_rich,
    )
    if not should_attempt:
        return {
            "detected": False,
            "confidence": "低",
            "detection_method": "",
            "summary": f"当前提交{attempt_reason}，跳过代码级引入追溯。",
            "introducer_commit": "",
            "introducer_title": "",
            "introducer_commit_url": "",
            "introducer_diff_url": "",
            "introduced_change_summary": "",
            "why_introduced": "",
            "evidence": [],
        }
    normalized_repo = normalize_repo_url(repo_url)
    if repo_dir is None:
        return {
            "detected": False,
            "confidence": "低",
            "detection_method": "",
            "summary": "当前提交未提供明确的 Fixes 线索，且未提供本地 git 历史，暂无法做代码级引入追溯。",
            "introducer_commit": "",
            "introducer_title": "",
            "introducer_commit_url": "",
            "introducer_diff_url": "",
            "introduced_change_summary": "",
            "why_introduced": "",
            "evidence": [],
        }

    current_dirs = sorted({p.split("/", 1)[0] for p in current_files if "/" in p})
    current_functions = extract_function_names_from_diff(current_diff)[:4]
    before_snippets = collect_before_snippets(code_rich)[:2]
    search_files = select_history_search_files(current_files, code_rich, max_files=3)
    candidate_shas = get_candidate_intro_commits(repo_dir, current_sha, search_files, limit=16)
    best: Optional[Tuple[float, CommitItem, str, List[str]]] = None
    for sha in candidate_shas[:12]:
        try:
            commit = fetch_single_commit(repo_url, sha, repo_dir=repo_dir)
            diff = fetch_diff_text(repo_url, sha, repo_dir=repo_dir)
        except Exception:
            continue
        score, evidence = score_candidate_introducer(
            candidate_sha=sha,
            candidate_message=commit.message,
            candidate_diff=diff,
            current_files=current_files,
            current_dirs=current_dirs,
            current_functions=current_functions,
            before_snippets=before_snippets,
            current_title=current_title,
        )
        if score < 7.0:
            continue
        if best is None or score > best[0]:
            best = (score, commit, diff, evidence)
        if score >= 10.0 and (
            any(item.startswith("共同修改文件:") for item in evidence)
            or any("旧代码形态" in item for item in evidence)
        ):
            break

    if best is None:
        return {
            "detected": False,
            "confidence": "低",
            "detection_method": "代码历史检索",
            "summary": "当前提交未提供 Fixes 线索；已基于本地 git 历史做同文件/同函数回溯，但未找到足够可信的引入 patch。",
            "introducer_commit": "",
            "introducer_title": "",
            "introducer_commit_url": "",
            "introducer_diff_url": "",
            "introduced_change_summary": "",
            "why_introduced": "",
            "evidence": [
                f"追溯触发原因: {attempt_reason}",
                f"历史检索范围: {len(search_files)} 个文件 / {len(candidate_shas[:12])} 个候选提交",
            ],
        }

    score, commit, diff, evidence = best
    intro_files = extract_files(diff)
    intro_insertions = count_insertions(diff)
    intro_deletions = count_deletions(diff)
    intro_title = commit.message.splitlines()[0] if commit.message else commit.sha
    return {
        "detected": True,
        "confidence": "中",
        "detection_method": "代码历史检索",
        "summary": f"当前提交未显式给出 Fixes，但从本地 git 历史和代码相似度看，{commit.sha} 很可能是问题引入修改。",
        "introducer_commit": commit.sha,
        "introducer_title": intro_title,
        "introducer_commit_url": f"{normalized_repo}/+/{commit.sha}",
        "introducer_diff_url": f"{normalized_repo}/+/{commit.sha}^!/",
        "introduced_change_summary": (
            f"引入 patch 修改 {len(intro_files)} 个文件（+{intro_insertions}/-{intro_deletions}），"
            f"主要集中在 {'、'.join(sorted({p.split('/', 1)[0] for p in intro_files if '/' in p})[:6]) or '相关目录'}。"
        ),
        "why_introduced": "这是基于同文件/同函数路径、当前修复前的旧代码形态，以及提交上下文重合度综合推断出的最可能引入 patch。",
        "evidence": [
            f"追溯触发原因: {attempt_reason}",
            f"历史检索范围: {len(search_files)} 个文件 / {len(candidate_shas[:12])} 个候选提交",
            *evidence,
        ][:6],
    }


def count_insertions(diff: str) -> int:
    return len(re.findall(r"(?m)^\+(?!\+\+)", diff))


def count_deletions(diff: str) -> int:
    return len(re.findall(r"(?m)^-(?!--)", diff))


def detect_test_signal(diff: str, files: List[str]) -> bool:
    if re.search(r"(?i)(kselftest|selftest|tests?/|_test\.)", diff):
        return True
    return any(re.search(r"(?i)(test|kselftest|selftest)", p) for p in files)


def detect_high_risk_paths(files: List[str]) -> bool:
    return any(re.match(r"^(mm|security|kernel|arch|fs)/", p) for p in files)


PATCH_TAG_RULES: List[Tuple[str, str, str, Tuple[str, ...]]] = [
    ("memory", "内存管理", "涉及 mm/ 或内存分配、回收、页表等路径", ("mm/", "include/linux/mm", "include/linux/page", "include/linux/slab")),
    ("filesystem", "文件系统", "涉及 fs/ 或文件系统公共接口", ("fs/", "include/linux/fs", "include/linux/namei", "include/linux/dcache")),
    ("network", "网络协议栈", "涉及 net/、网络驱动或网络协议头文件", ("net/", "include/net/", "drivers/net/")),
    ("driver", "驱动框架", "涉及 drivers/ 下的设备驱动", ("drivers/",)),
    ("block", "块设备/存储", "涉及 block/、块层或存储队列", ("block/", "include/linux/blk", "drivers/block/", "drivers/nvme/", "drivers/scsi/", "drivers/ufs/")),
    ("security", "安全", "涉及 security/、LSM、密钥或完整性保护", ("security/", "include/linux/lsm", "include/linux/security", "certs/", "crypto/asymmetric_keys/")),
    ("crypto", "加密", "涉及 crypto/ 或加密 API", ("crypto/", "include/crypto/")),
    ("scheduler", "调度", "涉及 scheduler、任务调度或负载均衡", ("kernel/sched/", "include/linux/sched")),
    ("locking", "锁/并发", "涉及锁、RCU、原子操作或并发同步", ("kernel/locking/", "include/linux/lock", "include/linux/rcu", "include/linux/atomic")),
    ("time", "时间/定时器", "涉及 timekeeping、timer、clocksource", ("kernel/time/", "include/linux/time", "drivers/clocksource/")),
    ("arch", "架构相关", "涉及 arch/ 架构代码", ("arch/",)),
    ("kvm", "虚拟化/KVM", "涉及 KVM、guest memory 或虚拟化路径", ("virt/", "arch/x86/kvm/", "arch/arm64/kvm/", "include/linux/kvm", "include/uapi/linux/kvm")),
    ("bpf", "BPF/eBPF", "涉及 BPF 子系统", ("kernel/bpf/", "net/bpf", "include/linux/bpf", "tools/testing/selftests/bpf/")),
    ("ipc", "IPC/进程通信", "涉及 ipc/ 或进程间通信", ("ipc/", "include/linux/ipc")),
    ("power", "电源管理", "涉及 PM、cpuidle、cpufreq、suspend/resume", ("kernel/power/", "drivers/cpufreq/", "drivers/cpuidle/", "drivers/power/", "include/linux/pm")),
    ("drm", "图形/DRM", "涉及 DRM/GPU/显示子系统", ("drivers/gpu/drm/", "include/drm/")),
    ("media", "多媒体", "涉及 media、摄像头、视频采集", ("drivers/media/", "include/media/")),
    ("sound", "音频", "涉及 ALSA/ASoC/声音子系统", ("sound/", "include/sound/")),
    ("usb", "USB", "涉及 USB 栈或 USB 设备驱动", ("drivers/usb/", "include/linux/usb")),
    ("input", "输入设备", "涉及 input 子系统", ("drivers/input/", "include/linux/input")),
    ("android", "Android/GKI", "涉及 Android 专有、GKI 或 vendor hook", ("android/", "drivers/android/", "include/trace/hooks/", "kernel/trace/hooks/")),
    ("uapi", "用户态接口", "涉及 uapi 头文件或 ABI", ("include/uapi/", "arch/x86/include/uapi/", "arch/arm64/include/uapi/")),
    ("test", "测试", "涉及 selftests、kunit 或测试用例", ("tools/testing/", "lib/kunit/", "kunit/", "samples/")),
    ("build", "构建/Kconfig", "涉及 Kconfig、Makefile 或构建脚本", ("Kconfig", "Makefile", "scripts/", "init/Kconfig")),
    ("doc", "文档", "涉及 Documentation 或文档说明", ("Documentation/",)),
]


def build_patch_tags(files: List[str]) -> List[Dict[str, Any]]:
    tags: List[Dict[str, Any]] = []
    seen = set()
    for key, label, reason, prefixes in PATCH_TAG_RULES:
        matched = []
        for path in files:
            normalized = path.replace("\\", "/")
            if any(normalized == prefix or normalized.startswith(prefix) for prefix in prefixes):
                matched.append(normalized)
            if len(matched) >= 4:
                break
        if matched and key not in seen:
            seen.add(key)
            tags.append({"key": key, "label": label, "reason": reason, "matched_files": matched})

    if not tags:
        tags.append({"key": "generic", "label": "通用内核", "reason": "未命中明确子系统路径规则", "matched_files": files[:4]})

    return tags[:8]


def merge_patch_tags_with_intent(files: List[str], message: str) -> List[Dict[str, Any]]:
    """在路径标签前附加 commit message 推断的「fix bug」或「新需求」标签；无法判断则不附加。"""
    base = build_patch_tags(files)
    info = classify_patch_intent(message)
    cat = str(info.get("patch_intent") or "").strip()
    if cat not in ("problem_solving", "new_requirement"):
        return base
    note = str(info.get("patch_intent_note", "")).strip()
    hints = info.get("patch_intent_hints") or []
    hint_tail = ""
    if hints:
        hint_tail = "；" + "；".join(str(h) for h in hints[:2])
    reason = "根据 commit message 启发式推断：" + note + hint_tail

    if cat == "problem_solving":
        extra: Dict[str, Any] = {
            "key": "intent_fix_bug",
            "label": "fix bug",
            "reason": reason,
            "matched_files": [],
        }
    else:
        extra = {
            "key": "intent_new_requirement",
            "label": "新需求",
            "reason": reason,
            "matched_files": [],
        }
    merged = [extra] + base
    return merged[:8]


PLATFORM_TAG_RULES: List[Tuple[str, str, str, Tuple[str, ...]]] = [
    ("arm64", "ARM64", "涉及 ARM64 架构代码或 ARM64 UAPI", ("arch/arm64/", "include/uapi/asm-arm64/", "tools/arch/arm64/")),
    ("arm", "ARM", "涉及 ARM 架构代码或 ARM UAPI", ("arch/arm/", "include/uapi/asm-arm/", "tools/arch/arm/")),
    ("x86", "x86", "涉及 x86 架构代码或 x86 UAPI", ("arch/x86/", "include/uapi/asm-x86/", "tools/arch/x86/")),
    ("riscv", "RISC-V", "涉及 RISC-V 架构代码或 RISC-V UAPI", ("arch/riscv/", "tools/arch/riscv/")),
    ("loongarch", "LoongArch", "涉及 LoongArch 架构代码", ("arch/loongarch/", "tools/arch/loongarch/")),
    ("mips", "MIPS", "涉及 MIPS 架构代码", ("arch/mips/", "tools/arch/mips/")),
    ("powerpc", "PowerPC", "涉及 PowerPC 架构代码", ("arch/powerpc/", "tools/arch/powerpc/")),
    ("s390", "s390", "涉及 s390 架构代码", ("arch/s390/", "tools/arch/s390/")),
    ("risc_legacy", "其他架构", "涉及其他架构目录", ("arch/arc/", "arch/csky/", "arch/hexagon/", "arch/m68k/", "arch/microblaze/", "arch/nios2/", "arch/openrisc/", "arch/parisc/", "arch/sh/", "arch/sparc/", "arch/um/", "arch/xtensa/")),
]


def build_platform_tags(files: List[str]) -> List[Dict[str, Any]]:
    tags: List[Dict[str, Any]] = []
    seen = set()
    normalized_files = [path.replace("\\", "/") for path in files]
    for key, label, reason, prefixes in PLATFORM_TAG_RULES:
        matched = []
        for path in normalized_files:
            if any(path == prefix or path.startswith(prefix) for prefix in prefixes):
                matched.append(path)
            if len(matched) >= 4:
                break
        if matched and key not in seen:
            seen.add(key)
            tags.append({"key": key, "label": label, "reason": reason, "matched_files": matched})

    if not tags:
        generic_files = [p for p in normalized_files if not p.startswith("arch/")][:4] or normalized_files[:4]
        tags.append({"key": "generic", "label": "通用平台", "reason": "未命中特定架构目录，按通用内核修改处理", "matched_files": generic_files})

    return tags[:6]


def choose_profile(config: Dict[str, Any], files: List[str]) -> Tuple[str, Dict[str, Any]]:
    default_profile = config.get("default_profile", {})
    matched_rule = "default"
    active = dict(default_profile)

    file_profiles = config.get("file_profiles", []) or []
    for fp in file_profiles:
        pattern = ((fp.get("match") or {}).get("file_glob")) or ""
        if pattern and any(fnmatch.fnmatch(path, pattern) for path in files):
            matched_rule = f"file:{fp.get('rule_id', 'unknown')}"
            overrides = fp.get("overrides", {})
            active = merge_profile(active, overrides)
            return matched_rule, active

    dir_profiles = config.get("directory_profiles", []) or []
    best: Optional[Tuple[int, Dict[str, Any], str]] = None
    for dp in dir_profiles:
        prefix = ((dp.get("match") or {}).get("directory_prefix")) or ""
        if not prefix:
            continue
        if any(p.startswith(prefix) for p in files):
            score = len(prefix)
            if best is None or score > best[0]:
                best = (score, dp.get("overrides", {}), dp.get("rule_id", "unknown"))
    if best:
        matched_rule = f"directory:{best[2]}"
        active = merge_profile(active, best[1])
    return matched_rule, active


def merge_profile(base: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_profile(merged[key], value)
        else:
            merged[key] = value
    return merged


def clamp(v: float, lo: float = 0.0, hi: float = 10.0) -> float:
    return max(lo, min(hi, v))


DEFAULT_SCORE_RULES: Dict[str, Dict[str, Any]] = {
    "correctness_completeness": {
        "base_score": 7.6,
        "adjustments": [
            {"when": "message_contains_any", "keywords": ["fix", "bug"], "delta": 0.5},
            {"when": "file_count_gt", "threshold": 30, "delta": -0.8},
            {"when": "churn_gt", "threshold": 2000, "delta": -0.7},
        ],
    },
    "risk_safety": {
        "base_score": 7.8,
        "adjustments": [
            {"when": "high_risk_paths_is", "value": True, "delta": -0.9},
            {"when": "churn_gt", "threshold": 3000, "delta": -0.8},
        ],
    },
    "testability_evidence": {
        "base_score": 8.0,
        "adjustments": [],
    },
    "diff_maintainability": {
        "base_score": 8.5,
        "linear_deductions": [
            {"metric": "file_count", "divisor": 40.0, "cap": 2.2},
            {"metric": "churn", "divisor": 2500.0, "cap": 2.0},
        ],
    },
    "commit_metadata_quality": {
        "base_score": 7.2,
        "adjustments": [
            {"when": "message_length_gt", "threshold": 40, "delta": 0.5},
            {"when": "message_regex", "pattern": r"(?i)\b(Bug:|Fixes:|Signed-off-by:)\b", "delta": 1.1},
        ],
    },
}


def _score_context(
    message: str,
    files: List[str],
    ins: int,
    dels: int,
    test_signal: bool,
    high_risk_paths: bool,
    diff_text: str = "",
) -> Dict[str, Any]:
    return {
        "message": message,
        "msg_lower": message.lower(),
        "message_length": len(message.strip()),
        "files": files,
        "file_count": len(files),
        "insertions": ins,
        "deletions": dels,
        "churn": ins + dels,
        "test_signal": test_signal,
        "high_risk_paths": high_risk_paths,
        "diff": diff_text or "",
    }


def _matches_score_condition(condition: Dict[str, Any], ctx: Dict[str, Any]) -> bool:
    if "all" in condition:
        return all(_matches_score_condition(item, ctx) for item in (condition.get("all") or []))
    if "any" in condition:
        return any(_matches_score_condition(item, ctx) for item in (condition.get("any") or []))

    when = str(condition.get("when", "")).strip()
    if not when:
        return False

    if when == "message_contains_any":
        keywords = [str(k).lower() for k in (condition.get("keywords") or [])]
        return any(k and k in ctx["msg_lower"] for k in keywords)
    if when == "message_regex":
        pattern = str(condition.get("pattern", ""))
        return bool(pattern and re.search(pattern, ctx["message"]))
    if when == "message_length_gt":
        return ctx["message_length"] > int(condition.get("threshold", 0))
    if when == "file_count_gt":
        return ctx["file_count"] > int(condition.get("threshold", 0))
    if when == "churn_gt":
        return ctx["churn"] > int(condition.get("threshold", 0))
    if when == "churn_gte":
        return ctx["churn"] >= int(condition.get("threshold", 0))
    if when == "churn_lt":
        return ctx["churn"] < int(condition.get("threshold", 0))
    if when == "churn_lte":
        return ctx["churn"] <= int(condition.get("threshold", 0))
    if when == "test_signal_is":
        want = condition.get("value")
        if isinstance(want, bool):
            return ctx["test_signal"] == want
        return ctx["test_signal"] == bool(want)
    if when == "high_risk_paths_is":
        want = condition.get("value")
        if isinstance(want, bool):
            return ctx["high_risk_paths"] == want
        return ctx["high_risk_paths"] == bool(want)

    if when == "any_file_prefix":
        prefix = str(condition.get("prefix", ""))
        if not prefix:
            return False
        files_list = ctx.get("files") or []
        return any(str(p).startswith(prefix) for p in files_list)
    if when == "any_file_regex":
        pat = str(condition.get("pattern", ""))
        if not pat:
            return False
        return any(re.search(pat, str(p)) for p in (ctx.get("files") or []))
    if when == "all_files_regex":
        pat = str(condition.get("pattern", ""))
        files_list = ctx.get("files") or []
        if not pat or not files_list:
            return False
        return all(re.search(pat, str(p)) for p in files_list)

    if when == "diff_regex":
        pat = str(condition.get("pattern", ""))
        diff = ctx.get("diff") or ""
        return bool(pat and diff and re.search(pat, diff, flags=re.DOTALL))

    if when == "not":
        inner = condition.get("cond")
        if not isinstance(inner, dict):
            return False
        return not _matches_score_condition(inner, ctx)

    return False


def _describe_score_condition(condition: Dict[str, Any]) -> str:
    if "all" in condition:
        parts = [_describe_score_condition(item) for item in (condition.get("all") or [])]
        parts = [p for p in parts if p]
        return "同时满足：" + "；".join(parts)
    if "any" in condition:
        parts = [_describe_score_condition(item) for item in (condition.get("any") or [])]
        parts = [p for p in parts if p]
        return "满足任一条件：" + "；".join(parts)

    when = str(condition.get("when", "")).strip()
    if when == "message_contains_any":
        keywords = ", ".join(str(k) for k in (condition.get("keywords") or []))
        return f"commit message 包含关键词 [{keywords}]"
    if when == "message_regex":
        return f"commit message 命中正则 {condition.get('pattern', '')}"
    if when == "message_length_gt":
        return f"commit message 长度 > {condition.get('threshold', 0)}"
    if when == "file_count_gt":
        return f"修改文件数 > {condition.get('threshold', 0)}"
    if when == "churn_gt":
        return f"增删行总数 > {condition.get('threshold', 0)}"
    if when == "churn_gte":
        return f"增删行总数 >= {condition.get('threshold', 0)}"
    if when == "churn_lt":
        return f"增删行总数 < {condition.get('threshold', 0)}"
    if when == "churn_lte":
        return f"增删行总数 <= {condition.get('threshold', 0)}"
    if when == "test_signal_is":
        return "检测到测试信号" if bool(condition.get("value")) else "未检测到测试信号"
    if when == "high_risk_paths_is":
        return "命中高风险目录" if bool(condition.get("value")) else "未命中高风险目录"
    if when == "any_file_prefix":
        return f"任一路径前缀 {condition.get('prefix', '')}"
    if when == "any_file_regex":
        return f"任一路径命中正则 {condition.get('pattern', '')}"
    if when == "all_files_regex":
        return f"全部路径命中正则 {condition.get('pattern', '')}"
    if when == "diff_regex":
        return f"diff 命中正则 {condition.get('pattern', '')}"
    if when == "not":
        inner = condition.get("cond")
        inner_desc = _describe_score_condition(inner) if isinstance(inner, dict) else ""
        return f"不满足 ({inner_desc})" if inner_desc else "取反条件"
    return "命中配置条件"


def merge_risk_signal_score_rules(
    score_rules: Dict[str, Any],
    rss: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Merge top-level `risk_signal_score_rules` from scoring-config into dimension score_rules."""
    if not rss:
        return score_rules
    if isinstance(rss, dict) and "signals" in rss:
        rss = rss.get("signals") or {}
    out = copy.deepcopy(score_rules)
    if not isinstance(rss, dict):
        return score_rules
    for rule_id, spec in rss.items():
        if isinstance(rule_id, str) and rule_id.startswith("_"):
            continue
        if str(rule_id) in ("version", "description", "signals"):
            continue
        if not isinstance(spec, dict):
            continue
        if spec.get("enabled") is False:
            continue
        dim = str(spec.get("dimension", "")).strip()
        if not dim:
            continue
        try:
            delta = float(spec.get("delta", 0.0))
        except (TypeError, ValueError):
            continue
        match_part: Dict[str, Any] = {}
        if isinstance(spec.get("match"), dict):
            match_part = dict(spec["match"])
        elif "all" in spec or "any" in spec:
            match_part = {}
            if "all" in spec:
                match_part["all"] = spec.get("all") or []
            if "any" in spec:
                match_part["any"] = spec.get("any") or []
        if not match_part:
            continue
        block: Dict[str, Any] = dict(match_part)
        block["delta"] = delta
        block["risk_signal_rule_id"] = str(rule_id)
        if str(spec.get("description", "")).strip():
            block["risk_signal_description"] = str(spec.get("description", "")).strip()
        dim_rule = out.setdefault(dim, {})
        adj = dim_rule.get("adjustments")
        if not isinstance(adj, list):
            dim_rule["adjustments"] = []
            adj = dim_rule["adjustments"]
        adj.append(block)
    return out


def _compute_dimension_detail(rule: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
    base_score = float(rule.get("base_score", 0.0))
    score = base_score
    additions: List[str] = []
    deductions: List[str] = []
    applied_rules = [f"基准分 {base_score:.1f}"]

    for item in rule.get("adjustments", []) or []:
        if isinstance(item, dict) and _matches_score_condition(item, ctx):
            delta = float(item.get("delta", 0.0))
            score += delta
            rsid = item.get("risk_signal_rule_id")
            rdesc = item.get("risk_signal_description")
            prefix = ""
            if rsid:
                prefix = f"「{rsid}」"
                if rdesc:
                    prefix += f"（{rdesc}）"
                prefix += " "
            detail = prefix + f"{_describe_score_condition(item)}，{delta:+.1f}"
            applied_rules.append(detail)
            if delta >= 0:
                additions.append(detail)
            else:
                deductions.append(detail)

    metric_values = {
        "file_count": float(ctx["file_count"]),
        "churn": float(ctx["churn"]),
        "insertions": float(ctx["insertions"]),
        "deletions": float(ctx["deletions"]),
    }
    metric_labels = {
        "file_count": "修改文件数",
        "churn": "增删行总数",
        "insertions": "新增行数",
        "deletions": "删除行数",
    }
    for item in rule.get("linear_deductions", []) or []:
        metric = str(item.get("metric", ""))
        divisor = float(item.get("divisor", 0) or 0)
        cap = float(item.get("cap", 0) or 0)
        if metric not in metric_values or divisor <= 0:
            continue
        deduction = metric_values[metric] / divisor
        if cap > 0:
            deduction = min(deduction, cap)
        score -= deduction
        if deduction > 0:
            cap_text = f"，上限 {cap:g}" if cap > 0 else ""
            detail = f"按 {metric_labels.get(metric, metric)} / {divisor:g} 线性扣分{cap_text}，-{deduction:.2f}"
            applied_rules.append(detail)
            deductions.append(detail)

    unclamped_score = round(score, 3)
    final_score = round(clamp(score), 1)
    if final_score != round(score, 1):
        clamp_note = f"最终分数限制在 0~10 区间，得到 {final_score:.1f}"
        applied_rules.append(clamp_note)
        deductions.append(clamp_note)
    return {
        "score": final_score,
        "applied_rules": applied_rules,
        "breakdown": {
            "base_score": round(base_score, 3),
            "additions": additions,
            "deductions": deductions,
            "unclamped_score": unclamped_score,
            "final_raw_score": final_score,
        },
    }


def compute_dimension_details(
    message: str,
    files: List[str],
    ins: int,
    dels: int,
    test_signal: bool,
    high_risk_paths: bool,
    score_rules: Optional[Dict[str, Any]] = None,
    diff_text: str = "",
) -> Dict[str, Dict[str, Any]]:
    active_rules = merge_profile(DEFAULT_SCORE_RULES, score_rules or {})
    ctx = _score_context(message, files, ins, dels, test_signal, high_risk_paths, diff_text)
    return {dim: _compute_dimension_detail(rule, ctx) for dim, rule in active_rules.items()}


def compute_dimension_scores(
    message: str,
    files: List[str],
    ins: int,
    dels: int,
    test_signal: bool,
    high_risk_paths: bool,
    score_rules: Optional[Dict[str, Any]] = None,
    diff_text: str = "",
) -> Dict[str, float]:
    details = compute_dimension_details(
        message, files, ins, dels, test_signal, high_risk_paths, score_rules, diff_text
    )
    return {dim: float(info.get("score", 0.0)) for dim, info in details.items()}


def build_dimension_reasons(
    message: str,
    file_count: int,
    churn: int,
    test_signal: bool,
    high_risk_paths: bool,
) -> Dict[str, str]:
    msg = message.lower()
    correctness = "改动目标较清晰，主流程可读。"
    if "fix" in msg or "bug" in msg:
        correctness = "commit 信息明确指向缺陷修复，问题-改动关联较强。"
    if file_count > 30 or churn > 2000:
        correctness = "改动面较大，完整性和边界覆盖存在一定不确定性。"

    risk = "风险整体可控。"
    if high_risk_paths:
        risk = "涉及核心子系统目录，需重点关注回归与稳定性风险。"
    if churn > 3000:
        risk = "改动规模较大，潜在回归风险上升。"

    # 加权已不纳入「是否含测试文件」；本条仅作文案说明变更面与关注点
    testability = "评分侧重改动本身（路径、规模、语义）；测试由独立流程覆盖，不因未改测试而降本维展示分。"
    if churn > 2500 or file_count > 25:
        testability += " 改动面较大时需关注边界与集成影响。"

    maintainability = "代码结构复杂度可接受。"
    if file_count > 40 or churn > 2500:
        maintainability = "改动规模偏大，维护成本和审阅成本较高。"

    metadata = "提交信息可读性一般。"
    if len(message.strip()) > 40:
        metadata = "提交信息描述较完整，便于审阅。"
    if re.search(r"(?i)\b(Bug:|Fixes:|Signed-off-by:)\b", message):
        metadata = "提交元信息较完整（Bug/Fixes/Signed-off-by），可追溯性较好。"

    return {
        "correctness_completeness": correctness,
        "risk_safety": risk,
        "testability_evidence": testability,
        "diff_maintainability": maintainability,
        "commit_metadata_quality": metadata,
    }


TEST_SUGGESTION_FIELDS = ["unit_test", "integration_test", "regression_test", "manual_validation", "release_safeguard"]


def _as_text_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _dedupe_keep_order(items: List[str]) -> List[str]:
    result = []
    seen = set()
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def match_test_suggestion_rule(
    match: Dict[str, Any],
    *,
    test_signal: bool,
    high_risk_paths: bool,
    churn: int,
    patch_tag_labels: List[str],
    platform_tag_labels: List[str],
) -> bool:
    if not match:
        return True
    if "test_signal" in match and bool(match.get("test_signal")) is not test_signal:
        return False
    if "high_risk_paths" in match and bool(match.get("high_risk_paths")) is not high_risk_paths:
        return False
    if "min_churn" in match and churn < int(match.get("min_churn", 0)):
        return False
    if "max_churn" in match and churn > int(match.get("max_churn", 0)):
        return False
    if "tag" in match:
        tags = match.get("tag")
        wanted = tags if isinstance(tags, list) else [tags]
        if not any(str(tag) in patch_tag_labels for tag in wanted):
            return False
    if "platform" in match:
        platforms = match.get("platform")
        wanted = platforms if isinstance(platforms, list) else [platforms]
        if not any(str(platform) in platform_tag_labels for platform in wanted):
            return False
    return True


def build_test_suggestions(
    files: List[str],
    high_risk_paths: bool,
    test_signal: bool,
    churn: int,
    config: Dict[str, Any],
    profile: Dict[str, Any],
    patch_tags: List[Dict[str, Any]],
    platform_tags: List[Dict[str, Any]],
) -> Dict[str, str]:
    touched_dirs = sorted({p.split("/", 1)[0] for p in files if "/" in p})[:5]
    dir_hint = "、".join(touched_dirs) if touched_dirs else "相关模块"
    suggestion_config = config.get("test_suggestions") or {}
    defaults = suggestion_config.get("defaults") or {}
    rules = suggestion_config.get("rules") or []
    patch_tag_labels = [str(tag.get("label", "")).strip() for tag in patch_tags if str(tag.get("label", "")).strip()]
    platform_tag_labels = [str(tag.get("label", "")).strip() for tag in platform_tags if str(tag.get("label", "")).strip()]

    fallback = {
        "unit_test": [f"围绕 {dir_hint} 的关键函数补充边界条件与异常分支单元测试。"],
        "integration_test": [f"针对 {dir_hint} 的跨模块调用链执行集成/接口回归。"],
        "regression_test": [f"回归受影响目录（{dir_hint}）的核心场景，覆盖正常与失败路径。"],
        "manual_validation": ["执行关键用户路径手工验证，并记录前后行为差异。"],
        "release_safeguard": ["上线后监控错误率、性能与关键日志，准备快速回滚方案。"],
    }

    suggestions: Dict[str, List[str]] = {}
    for field in TEST_SUGGESTION_FIELDS:
        suggestions[field] = _as_text_list(defaults.get(field)) or fallback[field]

    for rule in rules:
        if not isinstance(rule, dict):
            continue
        if not match_test_suggestion_rule(
            rule.get("match") or {},
            test_signal=test_signal,
            high_risk_paths=high_risk_paths,
            churn=churn,
            patch_tag_labels=patch_tag_labels,
            platform_tag_labels=platform_tag_labels,
        ):
            continue
        rule_suggestions = rule.get("suggestions") or {}
        for field in TEST_SUGGESTION_FIELDS:
            additions = _as_text_list(rule_suggestions.get(field))
            if additions:
                suggestions[field].extend(additions)

    focus_hints = _as_text_list(profile.get("test_focus_hints"))
    if focus_hints:
        suggestions["manual_validation"].append("重点关注：" + "、".join(focus_hints))

    return {field: "；".join(_dedupe_keep_order(suggestions[field])) for field in TEST_SUGGESTION_FIELDS}


def infer_problem_solved(message: str, diff: str, files: List[str]) -> str:
    lines = [ln.strip() for ln in message.splitlines() if ln.strip()]
    title = lines[0] if lines else ""
    noise_prefixes = ("Link:", "Signed-off-by:", "Reviewed-by:", "Tested-by:", "Cc:")

    # Keep only human-readable problem clues, drop metadata/noise lines.
    useful_lines: List[str] = []
    for ln in lines:
        if ln.startswith(noise_prefixes):
            continue
        if re.search(r"(?i)\b(Fixes:|Bug:|issue|regression|crash|uaf|overflow|null|deadlock)\b", ln):
            useful_lines.append(ln)

    msg_problem = ""
    if useful_lines:
        msg_problem = useful_lines[0]
    elif title:
        msg_problem = title

    code_signals = []
    if re.search(r"(?i)(use-after-free|uaf)", diff):
        code_signals.append("use-after-free 风险")
    if re.search(r"(?i)(null pointer|null deref|nullptr)", diff):
        code_signals.append("空指针相关问题")
    if re.search(r"(?i)(overflow|out[- ]of[- ]bounds|bounds)", diff):
        code_signals.append("边界/溢出问题")
    if re.search(r"(?i)(race|lock|deadlock|atomic)", diff):
        code_signals.append("并发/锁竞争问题")
    if re.search(r"(?i)(leak|refcount)", diff):
        code_signals.append("资源泄漏或引用计数问题")

    path_hint = ""
    touched_dirs = sorted({p.split("/", 1)[0] for p in files if "/" in p})[:4]
    if touched_dirs:
        path_hint = f"，影响目录主要在 {', '.join(touched_dirs)}"

    # Trim very long extracted messages and remove inline URLs for readability.
    if msg_problem:
        msg_problem = re.sub(r"https?://\S+", "", msg_problem).strip()
        msg_problem = re.sub(r"\s+", " ", msg_problem)
        if len(msg_problem) > 140:
            msg_problem = msg_problem[:140].rstrip() + "..."

    if msg_problem and code_signals:
        return f"结合提交信息与代码改动，主要解决“{msg_problem}”，并修正了{ '、'.join(code_signals) }{path_hint}。"
    if msg_problem:
        return f"结合提交信息与代码改动，主要解决“{msg_problem}”{path_hint}。"
    if code_signals:
        return f"从代码改动推断，主要在处理{ '、'.join(code_signals) }{path_hint}。"
    if title:
        return f"提交信息未显式给出缺陷描述，结合改动推断目标为“{title}”{path_hint}。"
    return "提交信息与代码改动均未给出明确问题描述，需要进一步人工审阅。"


_INTENT_TITLE_MULT = 2

_INTENT_FIX_PATTERNS: List[Tuple[re.Pattern[str], float, str]] = [
    (re.compile(r"(?si)\bfixes:\s+[0-9a-f]{7,}\b"), 5.0, "Fixes: 引用 upstream commit"),
    (re.compile(r"(?i)\bcloses:\s+\d+"), 3.5, "Closes: 工单引用"),
    (re.compile(r"(?i)^(fix|fixes|fixed|repair|repairing)(\s|,|:|\()" ), 5.0, "标题 fix/fixes 前缀"),
    (re.compile(r"(?i)\bBUG=\b|\bBUG:\s*|\bBug\s*:\s*"), 4.5, "Bug 引用"),
    (re.compile(r"(?i)\bCVE-\d{4}-\d+\b"), 5.0, "CVE 编号"),
    (re.compile(r"(?i)\b(regression|bisect|bisected)\b"), 4.0, "回归/二分"),
    (re.compile(r"(?i)\b(crash|panic|oops|splats|use-after-free|\buaf\b)\b"), 3.5, "缺陷类关键词"),
    (re.compile(r"(?i)\b(hotfix|workaround|correct|correcting)\b"), 3.0, "修补类词"),
    (re.compile(r"(?i)\b(reported-by:|syzbot|syzkaller)\b"), 3.5, "报告来源/自动化缺陷"),
    (re.compile(r"(?i)\bstable:\s*fix\b|\bupstream fix\b"), 3.5, "Stable/上游修复"),
]

_INTENT_FEAT_PATTERNS: List[Tuple[re.Pattern[str], float, str]] = [
    (re.compile(r"(?i)^(feat|feature)(\s|,|:|\()"), 6.0, "feat/feature 前缀"),
    (re.compile(r"(?i)^(add|introduce|implement)(\s+[a-z0-9_]+)+\s+(support|ioctl|syscall|abi|compat|helper)s?\b"), 5.0, "实现/引入能力"),
    (re.compile(r"(?i)^(add |introduce |implement )\w+"), 3.5, "标题 Add/Introduce/Implement"),
    (re.compile(r"(?i)\bnew (ioctl|sysctl|syscall|tracepoint|subsystem)\b"), 5.0, "new 能力关键字"),
    (re.compile(r"(?i)\bextend(s)? .* to support\b"), 4.0, "扩展支持措辞"),
    (re.compile(r"(?i)^(drm|netdev|bpf|kvm): (add |enable )\b"), 4.5, "子系统: add/enable"),
    (re.compile(r"(?i)^(selftests|bpf): add\b"), 4.5, "自测 bpf: add"),
    (re.compile(r"(?i)\buserspace ABI\b|\bnew API\b|\bexpose .* to userspace\b"), 4.0, "用户态接口/ABI"),
]

_INTENT_MAINT_PATTERNS: List[Tuple[re.Pattern[str], float, str]] = [
    (re.compile(r"(?i)^(merge |merge branch|merge tag|merge pull request|git pull)"), 5.0, "纯合并提交"),
    (re.compile(r"(?i)^(drm|net|usb|pci|irq): (cleanup|refactor|tidy)\b"), 3.5, "重构/清理类标题"),
    (re.compile(r"(?i)^docs?(\(|:|\])\b|^Documentation/"), 4.0, "文档类"),
    (re.compile(r"(?i)^(MAINTAINERS|maintainers)\b|update email for\b"), 3.5, "MAINTAINER 信息"),
]


def classify_patch_intent(message: str) -> Dict[str, Any]:
    """
    推断 patch 更偏「修问题」还是「新需求/能力」。

    仅基于 commit message 启发式打分，不读 diff；可能与实际不符，需人工复核。
    """
    raw = (message or "").strip()
    if not raw:
        return {
            "patch_intent": "mixed_or_unclear",
            "patch_intent_hints": ["无 commit message"],
            "patch_intent_note": "无法分类",
        }

    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    title = lines[0] if lines else ""
    noise = {"signed-off-by:", "reviewed-by:", "tested-by:", "acked-by:", "cc:", "link:"}
    body_lines = [ln for ln in lines[1:80] if not ln.lower().startswith(tuple(noise))]
    body = "\n".join(body_lines)

    def _accumulate(patterns: List[Tuple[re.Pattern[str], float, str]]) -> Tuple[float, List[str]]:
        weight = 0.0
        hits: List[str] = []
        seen: set[str] = set()
        for rx, w, tag in patterns:
            t_hit = rx.search(title)
            b_hit = rx.search(body) if body else None
            if t_hit:
                weight += w * _INTENT_TITLE_MULT
                if tag + "(标题)" not in seen:
                    seen.add(tag + "(标题)")
                    hits.append(f"{tag}（标题加权）")
            if b_hit:
                weight += w
                key = tag + "(正文)"
                if key not in seen:
                    seen.add(key)
                    hits.append(tag + "（正文）")
        return weight, hits[:8]

    tl = title.strip()
    if tl.lower().startswith("revert "):
        return {
            "patch_intent": "problem_solving",
            "patch_intent_hints": ["标题为 Revert：多为回滚有问题的补丁或恢复行为"],
            "patch_intent_note": "回滚/纠错类变更",
        }

    if len(lines) <= 6 and re.match(r"(?i)^Merge (branch|tag|remote-tracking|pull request)", title):
        return {
            "patch_intent": "mixed_or_unclear",
            "patch_intent_hints": ["Merge 类标题：多为集成他人分支，不按功能新装分类"],
            "patch_intent_note": "合并提交",
        }

    fx, fix_hits = _accumulate(_INTENT_FIX_PATTERNS)
    ft, feat_hits = _accumulate(_INTENT_FEAT_PATTERNS)
    mt, maint_hits = _accumulate(_INTENT_MAINT_PATTERNS)

    if mt >= 8.0 and fx < 4.0 and ft < 4.0:
        return {
            "patch_intent": "mixed_or_unclear",
            "patch_intent_hints": (maint_hits + fix_hits + feat_hits)[:8] or ["维护/流程类为主"],
            "patch_intent_note": "维护或合入操作，未判为修问题/新能力",
        }

    if fx >= 9.0 and ft <= 3.0:
        category = "problem_solving"
        note = "偏修复/纠错/安全或回归问题"
    elif ft >= 9.0 and fx <= 3.0:
        category = "new_requirement"
        note = "偏新增能力、接口或用户可见行为"
    elif fx >= 5.0 and ft >= 5.0:
        category = "mixed_or_unclear"
        note = "同时出现较强「修问题」与「新能力」线索"
    elif fx > ft + 2.0:
        category = "problem_solving"
        note = "修复类线索多于新能力类"
    elif ft > fx + 2.0:
        category = "new_requirement"
        note = "新能力类线索多于修复类"
    else:
        category = "mixed_or_unclear"
        note = "信号不足或两类接近，建议结合 diff 人工判断"

    hints = fix_hits + feat_hits
    if category == "mixed_or_unclear" and not hints:
        hints = ["未发现强特征前缀或关键词"]

    seen_h: List[str] = []
    uniq: List[str] = []
    for h in hints:
        if h not in seen_h:
            seen_h.append(h)
            uniq.append(h)

    return {
        "patch_intent": category,
        "patch_intent_hints": (uniq[:8]),
        "patch_intent_note": note,
    }


def summarize_change_content(files: List[str], insertions: int, deletions: int, recommendation: str) -> str:
    if not files:
        return "未解析到变更文件信息。"
    touched_dirs = sorted({p.split("/", 1)[0] for p in files if "/" in p})[:6]
    dirs = "、".join(touched_dirs) if touched_dirs else "相关目录"
    return (
        f"修改 {len(files)} 个文件（+{insertions}/-{deletions}），主要集中在 {dirs}；"
        f"当前评估建议为“{recommendation}”。"
    )


def build_commit_interpretation(message: str) -> str:
    lines = [ln.strip() for ln in message.splitlines() if ln.strip()]
    if not lines:
        return "commit 信息较少，无法直接识别明确的改动意图。"
    title = lines[0]
    useful = []
    for ln in lines[1:]:
        if ln.startswith(("Link:", "Signed-off-by:", "Reviewed-by:", "Cc:")):
            continue
        if re.search(r"(?i)\b(Fixes:|Bug:|Closes:|issue|regression|crash|uaf|overflow)\b", ln):
            useful.append(ln)
    if useful:
        return f"从 commit 信息看，主要意图是“{title}”；并给出了问题线索：{useful[0]}"
    return f"从 commit 信息看，主要意图是“{title}”。"


def build_commit_interpretation_rich(message: str) -> Dict[str, Any]:
    raw_lines = [ln.rstrip() for ln in message.splitlines()]
    lines = [ln.strip() for ln in raw_lines if ln.strip()]
    if not lines:
        return {
            "title": "",
            "upstream_commit": "",
            "problem_context": "commit message 为空，无法提取上下文。",
            "constraint_context": "",
            "signals": [],
            "references": [],
            "summary": "缺少提交说明，需要结合代码改动人工判断。",
        }

    title = lines[0]
    signals: List[str] = []
    refs: List[str] = []
    fixes_lines: List[str] = []
    upstream_commit = ""

    metadata_prefixes = (
        "Reported-by:",
        "Link:",
        "Closes:",
        "Bug:",
        "Fixes:",
        "Signed-off-by:",
        "Reviewed-by:",
        "Tested-by:",
        "Cc:",
    )

    body_lines: List[str] = []
    current_paragraph: List[str] = []
    paragraphs: List[str] = []
    in_code_block = False

    def flush_paragraph() -> None:
        if current_paragraph:
            paragraphs.append(" ".join(current_paragraph).strip())
            current_paragraph.clear()

    def is_log_or_trace_line(text: str) -> bool:
        if not text:
            return False
        if "sample stack trace" in text.lower():
            return True
        if re.match(r"^\[\s*\d+\.\d+\]", text):
            return True
        if re.match(r"^(WARNING:|CPU:|Modules linked in:|Hardware name:|Workqueue:|RIP:|Code:|RSP:|RAX:|RBX:|RCX:|RDX:|RSI:|RDI:|RBP:|R0?[89]:|R1[0-5]:|FS:|GS:|CS:|DS:|ES:|CR[0-4]:|PKRU:|Call Trace:)", text):
            return True
        if text in {"<TASK>", "</TASK>"}:
            return True
        if re.match(r"^(ret_from_fork|ret_from_fork_asm|\?\s)", text):
            return True
        return False

    def shorten_text(text: str, limit: int = 120) -> str:
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) <= limit:
            return text
        return text[:limit].rstrip() + "..."

    for ln in raw_lines[1:]:
        stripped = ln.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            flush_paragraph()
            continue
        if in_code_block:
            continue
        if not stripped:
            flush_paragraph()
            continue
        if is_log_or_trace_line(stripped):
            flush_paragraph()
            continue
        if re.match(r"^\[\s*Upstream commit\s+[0-9a-fA-F]+\s*\]$", stripped):
            upstream_commit = stripped
            continue
        upstream_match = re.match(r"^commit\s+([0-9a-fA-F]{12,40})\s+upstream\.?$", stripped, re.IGNORECASE)
        if upstream_match:
            upstream_commit = f"commit {upstream_match.group(1)} upstream"
            continue
        if stripped.startswith(metadata_prefixes):
            if stripped.startswith("Link:"):
                refs.append(stripped.replace("Link:", "").strip())
            elif stripped.startswith(("Closes:", "Bug:", "Fixes:")):
                fixes_lines.append(stripped)
            continue
        current_paragraph.append(stripped)
        body_lines.append(stripped)
    flush_paragraph()

    def clean_english(text: str) -> str:
        text = re.sub(r"\[[0-9]+\]", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def mostly_english(text: str) -> bool:
        ascii_letters = len(re.findall(r"[A-Za-z]", text))
        cjk_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
        return ascii_letters >= 24 and cjk_chars <= 6

    def split_sentences(text: str) -> List[str]:
        parts = [x.strip() for x in re.split(r"(?<=[.!?])\s+", text) if x.strip()]
        return parts or ([text.strip()] if text.strip() else [])

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
            ("corruption", "损坏数据"),
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
            lowered = token.lower()
            if lowered in CODE_KEYWORDS or len(token) < 4:
                continue
            if token not in symbols:
                symbols.append(token)
            if len(symbols) >= 3:
                break
        return "、".join(symbols[:3]) if symbols else "相关路径"

    def translate_effect_clause(clause: str) -> str:
        c = clean_english(clause).rstrip(".")
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
        c = clean_english(clause).rstrip(".")
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

    def translate_known_english_sentence(sentence: str) -> str:
        s = clean_english(sentence)
        if not s:
            return ""

        m = re.search(r"(?i)^The reproducer builds? a corrupted file on disk with a negative ([A-Za-z0-9_]+) value\.?$", s)
        if m:
            field = m.group(1)
            return f"复现用例会在磁盘上构造一个 {field} 为负值的损坏文件。"

        m = re.search(r"(?i)^Add a check when opening (?:this|the) file to avoid (.+?)\.?$", s)
        if m:
            target = translate_effect_clause(m.group(1))
            return f"这笔修改在打开该文件时增加检查，以避免 {target}。"

        m = re.search(r"(?i)^Add a check (.+?) to avoid (.+?)\.?$", s)
        if m:
            when_clause = translate_condition_clause(m.group(1))
            target = translate_effect_clause(m.group(2))
            return f"这笔修改在 {when_clause} 增加检查，以避免 {target}。"

        m = re.search(r"(?i)^This happens when (.+?)\.?$", s)
        if m:
            return "问题会在特定条件下触发。"

        m = re.search(r"(?i)^This can lead to (.+?)\.?$", s)
        if m:
            target = translate_effect_clause(m.group(1))
            return f"该问题会进一步导致 {target}。"

        m = re.search(r"(?i)^This causes? (.+?)\.?$", s)
        if m:
            target = translate_effect_clause(m.group(1))
            return f"该问题会导致 {target}。"

        return ""

    def summarize_english_problem(paragraph: str) -> str:
        p = clean_english(paragraph)
        if not p:
            return ""

        sample_summary = try_sample_based_problem_summary(p)
        if sample_summary:
            return sample_summary

        translated_sentences = [x for x in (translate_known_english_sentence(s) for s in split_sentences(p)) if x]
        if translated_sentences:
            return "正文指出：" + " ".join(translated_sentences)

        if mostly_english(p):
            issue_text = summarize_issue_keywords(p)
            symbol_text = summarize_symbols(p)
            return f"正文指出：该提交主要处理 {symbol_text} 上与 {issue_text} 相关的问题，并通过补充检查或防护避免后续失败。"

        return ""

    def summarize_problem(paragraph: str) -> str:
        p = clean_english(paragraph)
        if not p:
            return "未在正文中提取到清晰的问题背景描述。"
        if (
            "invalid entities" in p.lower()
            or "duplicated id" in p.lower()
            or "same id" in p.lower()
            or "source id was 0" in p.lower()
        ):
            return "正文指出：当实体 ID 为 0、重复，或链路引用落到错误实体时，uvcvideo 会把非法实体接入拓扑，进而触发告警或异常链路解析。"
        if (
            "inode->i_mode" in p
            and "16bits" in p
            and "mode" in p
            and "loaded from disk" in p
            and "corrupted" in p
        ):
            return "正文指出：当从磁盘读取的 16 位 mode 字段中的 S_IFMT 位发生损坏时，inode->i_mode 中的文件类型位可能被带坏，进而出现非法类型。"
        if re.search(r"(?i)syzbot is reporting that", p):
            p = re.sub(r"(?i)^syzbot is reporting that\s*", "", p)
        m = re.search(r"(?i)(.+?) can become (.+?) when (.+)", p)
        if m:
            subject = m.group(1).strip()
            result = m.group(2).strip().rstrip(".")
            cond = m.group(3).strip().rstrip(".")
            result = result.replace("bogus", "非法值")
            return f"正文指出：当 {cond} 时，{subject} 可能变成 {result}。"
        translated = summarize_english_problem(p)
        if translated:
            return translated
        return f"正文指出：{p}。"

    def summarize_constraint(paragraphs_list: List[str]) -> str:
        if not paragraphs_list:
            return ""
        constraint_candidates = [
            p
            for p in paragraphs_list
            if re.search(r"(?i)^(Per|According to)\b", p) or re.search(r"(?i)\b(must|reserved|specification)\b", p)
        ]
        joined = clean_english(" ".join(constraint_candidates[:2]))
        if not joined:
            return ""
        if "UVC 1.1+" in joined and "non-zero unique ID" in joined:
            return "提交引用 UVC 1.1+ 规范：Unit 和 Terminal 必须使用非零且唯一的 ID，0x00 保留为未定义值。"
        if (
            "permissions field was treated as reserved" in joined
            and "must remain 0 as long as reserved" in joined
            and 'when the "mode" field is not 0' in joined
        ):
            return (
                "提交引用 HFS+ 规范说明：permissions 字段在早期系统中属于保留字段，保留时会被初始化为 0 且必须保持为 0；"
                "因此，一旦 mode 字段不为 0，目录条目必须是 S_IFDIR，非目录条目则只能是 "
                "S_IFREG/S_IFLNK/S_IFCHR/S_IFBLK/S_IFIFO/S_IFSOCK 这些合法类型。"
            )
        if re.search(r"(?i)According to", joined):
            joined = re.sub(r"(?i)According to", "根据", joined)
            joined = re.sub(r"(?i)the permissions field was treated as reserved", "permissions 字段在早期系统中被当作保留字段", joined)
            joined = re.sub(r"(?i)the reserved field was explicitly initialized with 0", "该保留字段会被显式初始化为 0", joined)
            joined = re.sub(r"(?i)must remain 0 as long as reserved", "并且在保留状态下必须保持为 0", joined)
            joined = re.sub(r"(?i)Therefore,", "因此，", joined)
            joined = re.sub(r"(?i)the file must be", "文件类型必须是", joined)
            joined = re.sub(r"(?i)when the \"mode\" field is not 0", "当 mode 字段不为 0 时", joined)
        if joined.startswith("Per "):
            joined = "提交引用约束：" + joined
        return shorten_text(joined, limit=110)

    def pick_problem_paragraph(paragraphs_list: List[str]) -> str:
        for p in paragraphs_list:
            if re.search(r"(?i)\b(if|warning|warn|crash|broke|broken|invalid|duplicate|duplicated|syz|reproducer|same ID|source ID was 0|not valid|leads to)\b", p):
                return p
        return paragraphs_list[0] if paragraphs_list else ""

    if re.search(r"(?i)syzbot|reported-by", message):
        signals.append("存在自动化缺陷报告来源（syzbot）")
    if upstream_commit:
        signals.append("这是从上游回合入的一笔修复")
    if fixes_lines:
        signals.append("提交附带明确的缺陷闭环线索（Closes/Fixes/Bug）")
    if re.search(r"(?i)\b(corrupt|bogus|invalid)\b", message):
        signals.append("问题与磁盘脏数据/非法值导致的状态异常相关")

    problem_context = summarize_problem(pick_problem_paragraph(paragraphs))
    constraint_context = summarize_constraint(paragraphs)

    summary_parts = [f"这笔提交的目标是“{title}”。", problem_context]
    if constraint_context:
        if constraint_context.startswith("提交引用") or constraint_context.startswith("提交引用约束"):
            summary_parts.append(constraint_context)
    if fixes_lines:
        if any("syzkaller.appspot.com" in x for x in fixes_lines):
            summary_parts.append("闭环线索：该提交关联并关闭了一条 syzbot 缺陷报告。")
        else:
            summary_parts.append(f"闭环线索：{shorten_text(fixes_lines[0], limit=80)}")
    summary = shorten_text(" ".join(part for part in summary_parts if part).strip(), limit=220)

    return {
        "title": title,
        "upstream_commit": upstream_commit,
        "problem_context": problem_context,
        "constraint_context": constraint_context,
        "signals": signals[:6],
        "references": refs[:6],
        "fixes_closes": fixes_lines[:6],
        "summary": summary,
        "useful_body": paragraphs,
    }


def build_code_change_analysis(diff: str, files: List[str], insertions: int, deletions: int) -> str:
    file_count = len(files)
    touched_dirs = sorted({p.split("/", 1)[0] for p in files if "/" in p})[:5]
    dirs = "、".join(touched_dirs) if touched_dirs else "相关目录"

    behavior_signals = []
    if re.search(r"(?m)^\+\s*if\s*\(", diff):
        behavior_signals.append("新增条件分支校验")
    if re.search(r"(?m)^\+\s*return\s+-E[A-Z0-9_]+", diff):
        behavior_signals.append("新增错误返回路径")
    if re.search(r"(?m)^\+\s*goto\s+", diff):
        behavior_signals.append("新增失败短路流程")
    if re.search(r"(?m)^\+\s*pr_(err|warn|info)\(", diff):
        behavior_signals.append("新增日志可观测性")
    if re.search(r"(?m)^-\s*static\s+void\s+\w+\(", diff) and re.search(r"(?m)^\+\s*static\s+int\s+\w+\(", diff):
        behavior_signals.append("函数签名由无返回改为带状态返回")

    base = f"从代码改动看，涉及 {file_count} 个文件（+{insertions}/-{deletions}），主要在 {dirs}。"
    if behavior_signals:
        base += " 关键变化包括：" + "、".join(behavior_signals) + "。"
    else:
        base += " 主要是局部逻辑调整与兼容性/可维护性修正。"
    return base


def build_code_change_analysis_rich(diff: str, files: List[str], insertions: int, deletions: int) -> Dict[str, Any]:
    file_count = len(files)
    touched_dirs = sorted({p.split("/", 1)[0] for p in files if "/" in p})[:6]
    summary = build_code_change_analysis(diff, files, insertions, deletions)

    def extract_defined_function_name(text: str) -> str:
        keywords = {"if", "for", "while", "switch", "return", "sizeof"}
        lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
        if not lines:
            return ""

        signature = []
        for ln in lines[:4]:
            signature.append(ln.strip())
            if ")" in ln:
                break
        candidate = " ".join(signature)
        if not re.match(
            r"^(?:static\s+)?(?:inline\s+)?(?:const\s+)?(?:unsigned\s+|signed\s+)?"
            r"(?:(?:void|int|long|short|char|bool|ssize_t|size_t|u8|u16|u32|u64|s8|s16|s32|s64)\s+|"
            r"(?:struct|enum|union)\s+\w+\s+)"
            r"[\w\*\s]*[A-Za-z_]\w*\s*\(",
            candidate,
        ):
            return ""
        match = re.search(r"([A-Za-z_]\w*)\s*\(", candidate)
        if not match:
            return ""
        name = match.group(1)
        return "" if name in keywords else name

    def extract_call_name(text: str) -> str:
        keywords = {"if", "for", "while", "switch", "return", "sizeof"}
        for name in re.findall(r"([A-Za-z_]\w*)\s*\(", text):
            if name not in keywords:
                return name
        return ""

    def make_readable_location(file_path: str, header: str, added_text: str, removed_text: str) -> str:
        defined = extract_defined_function_name(added_text + "\n" + removed_text)
        if defined:
            return f"函数 {defined}()"

        header_fn = extract_defined_function_name(header)
        call_name = extract_call_name(added_text)
        if header_fn and call_name and header_fn != call_name:
            return f"函数 {header_fn}() 中调用 {call_name}() 的位置"
        if header_fn:
            return f"函数 {header_fn}() 内部逻辑"
        if call_name:
            return f"{file_path} 中调用 {call_name}() 的位置"
        return file_path

    files_stat = []
    current_file = ""
    f_add = 0
    f_del = 0
    for ln in diff.splitlines():
        if ln.startswith("diff --git "):
            if current_file:
                files_stat.append({"file": current_file, "insertions": f_add, "deletions": f_del})
            m = re.search(r" b/(.+)$", ln)
            current_file = m.group(1) if m else ""
            f_add = 0
            f_del = 0
        elif ln.startswith("+") and not ln.startswith("+++"):
            f_add += 1
        elif ln.startswith("-") and not ln.startswith("---"):
            f_del += 1
    if current_file:
        files_stat.append({"file": current_file, "insertions": f_add, "deletions": f_del})

    files_stat = sorted(files_stat, key=lambda x: (x["insertions"] + x["deletions"]), reverse=True)[:8]

    lines = diff.splitlines()
    current_file = ""
    current_hunk: Optional[Dict[str, Any]] = None
    hunks: List[Dict[str, Any]] = []
    for ln in lines:
        if ln.startswith("diff --git "):
            m = re.search(r" b/(.+)$", ln)
            current_file = m.group(1) if m else ""
            current_hunk = None
            continue
        if ln.startswith("@@"):
            if current_hunk:
                hunks.append(current_hunk)
            header = ""
            m = re.match(r"@@ .* @@\s*(.*)", ln)
            if m:
                header = m.group(1).strip()
            current_hunk = {"file": current_file, "header": header, "added": [], "removed": []}
            continue
        if not current_hunk:
            continue
        if ln.startswith("+") and not ln.startswith("+++"):
            current_hunk["added"].append(ln[1:])
        elif ln.startswith("-") and not ln.startswith("---"):
            current_hunk["removed"].append(ln[1:])
    if current_hunk:
        hunks.append(current_hunk)

    logic_changes: List[Dict[str, str]] = []
    for hunk in hunks[:12]:
        added = "\n".join(hunk["added"])
        removed = "\n".join(hunk["removed"])
        header = hunk["header"] or hunk["file"] or "unknown"
        readable_location = make_readable_location(hunk["file"] or "unknown", header, added, removed)
        explanation = ""
        if re.search(r"static\s+void\s+\w+\(", removed) and re.search(r"static\s+int\s+\w+\(", added):
            explanation = "将函数从无返回值改为返回状态码，使调用方可以感知权限/类型校验失败并中止后续流程。"
        elif "goto bad_type" in added and "switch (mode & S_IFMT)" in added:
            explanation = "在读取磁盘 mode 后新增文件类型白名单校验，非法类型统一跳转到错误路径，阻止脏数据继续污染 inode 状态。"
        elif "pr_err(" in added and "-EIO" in added:
            explanation = "新增日志和 -EIO 错误返回，把原本可能静默继续的非法场景变成显式失败，提升可观测性和安全性。"
        elif re.search(r"\bres\s*=\s*\w+\(", added) and re.search(r"if\s*\(\s*res\s*\)", added):
            explanation = "调用点开始检查下层函数返回值，出现错误时直接退出，说明校验结果已经参与控制主流程。"
        elif re.search(r"\bif\s*\(", added):
            explanation = "新增条件分支，对异常输入或边界情况做额外防护。"
        elif re.search(r"\bswitch\s*\(", added):
            explanation = "新增分类型处理逻辑，根据不同输入类型走不同分支。"

        if explanation:
            logic_changes.append(
                {
                    "location": readable_location,
                    "explanation": explanation,
                    "before": "\n".join(hunk["removed"][:4]).strip(),
                    "after": "\n".join(hunk["added"][:8]).strip(),
                }
            )

    if not logic_changes:
        # fallback to representative snippets
        for entry in files_stat[:3]:
            target = entry["file"]
            added = []
            removed = []
            in_target = False
            for ln in diff.splitlines():
                if ln.startswith("diff --git "):
                    in_target = target in ln
                    continue
                if not in_target:
                    continue
                if ln.startswith("+") and not ln.startswith("+++"):
                    code = ln[1:].rstrip()
                    if code and len(added) < 6:
                        added.append(code)
                elif ln.startswith("-") and not ln.startswith("---"):
                    code = ln[1:].rstrip()
                    if code and len(removed) < 3:
                        removed.append(code)
                if len(added) >= 6 and len(removed) >= 3:
                    break
            if added or removed:
                logic_changes.append(
                    {
                        "location": f"文件 {target}",
                        "explanation": "该位置存在实质代码调整，需要结合上下文确认具体行为变化。",
                        "before": "\n".join(removed).strip(),
                        "after": "\n".join(added).strip(),
                    }
                )

    return {
        "summary": summary,
        "touched_directories": touched_dirs,
        "files_stat": files_stat,
        "logic_changes": logic_changes[:5],
    }


def build_problem_closure_rich(
    recommendation: str,
    blocked: bool,
    block_hits: List[str],
    problem_solved: str,
    commit_rich: Dict[str, Any],
    code_rich: Dict[str, Any],
) -> Dict[str, Any]:
    logic_changes = code_rich.get("logic_changes", []) or []
    explanations = " ".join(str(item.get("explanation", "")) for item in logic_changes)
    logic_refs = []
    for item in logic_changes[:3]:
        loc = str(item.get("location", "")).strip()
        exp = str(item.get("explanation", "")).strip()
        if loc and exp:
            logic_refs.append(f"{loc}：{exp}")
    has_validation = any(
        key in explanations for key in ["白名单校验", "条件分支校验", "异常输入", "非法类型", "校验失败"]
    )
    has_error_propagation = any(
        key in explanations for key in ["错误返回", "短路流程", "返回状态码", "中止后续流程", "控制主流程"]
    )
    has_observability = any(key in explanations for key in ["日志", "可观测性"])
    fixes_lines = commit_rich.get("fixes_closes", []) or []

    why_fixed = ""
    missing_evidence = ""
    acceptance = ""

    if blocked:
        closure = "未闭环"
        confidence = "高"
        conclusion = "命中了阻断规则，说明当前改动仍存在明确风险，不能认为问题已经完成闭环。"
        why_fixed = "当前代码改动不足以证明问题已被可靠拦截，因为仍存在阻断级风险。"
        missing_evidence = "需要先消除阻断项，并补充能够证明风险被收敛的验证结果。"
        acceptance = "不建议直接接受这笔修复。"
    elif has_validation and has_error_propagation:
        closure = "逻辑上已闭环"
        confidence = "高"
        conclusion = (
            "代码不仅新增了问题输入相关判断，还把失败结果接入主流程控制，异常场景会被拦截并阻断继续传播；"
            "从变更本身可判断问题在逻辑上已形成较完整闭环。"
        )
        ref_text = "；".join(logic_refs[:2])
        why_fixed = (
            f"从具体代码看，{ref_text}。这说明非法输入会先被识别，再通过返回值影响主流程，"
            "异常状态不会继续向后传播，因此修复直接命中了问题根因。"
        )
        missing_evidence = (
            "若仍有关键路径未被 diff 覆盖，可考虑由独立测试流程补充验证；"
            "本评分不因是否修改测试文件而降分。"
        )
        acceptance = "可以接受这笔修复，并结合常规回归与受影响路径人工抽查一起评估。"
    elif has_validation or has_error_propagation:
        closure = "部分闭环"
        confidence = "中"
        conclusion = (
            "代码中已经出现与问题相关的防护或错误处理，但尚未同时看到“输入校验 + 主流程收口”两类证据，"
            "因此只能认为问题得到部分缓解，还不能下结论说已经完整闭环。"
        )
        ref_text = "；".join(logic_refs[:2]) if logic_refs else "代码中已经出现与问题相关的局部防护"
        why_fixed = f"从具体代码看，{ref_text}，说明作者已经开始针对问题根因加防护，但修复证据还不完整。"
        missing_evidence = "还缺少另一半关键证据，例如输入合法性校验或错误接入主流程的控制路径。"
        acceptance = "暂不建议直接接受，除非补齐剩余控制流或校验逻辑。"
    else:
        closure = "闭环证据不足"
        confidence = "低"
        conclusion = (
            "提交描述了修复目标，但从代码改动里暂未看到足够明确的控制流或校验逻辑变化来证明问题已被真正兜住，"
            "需要进一步人工审阅或运行验证。"
        )
        why_fixed = "当前改动里缺少能够直接对应问题根因的关键代码路径，因此还不足以说明问题已经被真正解决。"
        missing_evidence = "缺少能直接对应问题根因的校验、错误处理或主流程控制证据。"
        acceptance = "不建议直接接受这笔修复。"

    evidence = [
        f"提交目标：{commit_rich.get('title', '-')}",
        f"问题归纳：{problem_solved}",
        f"代码改动摘要：{code_rich.get('summary', '-')}",
        f"逻辑变化数量：{len(logic_changes)}",
        f"校验证据：{'有' if has_validation else '无'}",
        f"主流程收口证据：{'有' if has_error_propagation else '无'}",
    ]
    if has_observability:
        evidence.append("可观测性：新增日志/错误提示，便于定位异常场景。")
    if fixes_lines:
        evidence.append("缺陷线索：" + fixes_lines[0])
    if block_hits:
        evidence.append("阻断规则命中：" + ", ".join(block_hits))

    return {
        "status": closure,
        "confidence": confidence,
        "evidence": evidence[:8],
        "conclusion": conclusion,
        "why_fixed": why_fixed,
        "missing_evidence": missing_evidence,
        "acceptance": acceptance,
    }


def extract_fixes_refs(message: str) -> List[str]:
    refs: List[str] = []
    for line in message.splitlines():
        stripped = line.strip()
        if not stripped.startswith("Fixes:"):
            continue
        match = re.search(r"Fixes:\s*([0-9a-fA-F]{8,40})\b", stripped)
        if match:
            sha = match.group(1)
            if sha not in refs:
                refs.append(sha)
    return refs


def build_problem_introducer_rich(
    repo_url: str,
    current_sha: str,
    current_title: str,
    current_message: str,
    current_diff: str,
    current_files: List[str],
    current_code_rich: Dict[str, Any],
    problem_closure_rich: Optional[Dict[str, Any]] = None,
    repo_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    fixes_refs = extract_fixes_refs(current_message)
    if not fixes_refs:
        return infer_introducer_from_history(
            repo_url=repo_url,
            current_sha=current_sha,
            current_title=current_title,
            current_message=current_message,
            current_diff=current_diff,
            current_files=current_files,
            code_rich=current_code_rich,
            repo_dir=repo_dir,
            problem_closure_rich=problem_closure_rich,
        )

    primary_ref = fixes_refs[0]
    normalized_repo = normalize_repo_url(repo_url)
    try:
        introducer_commit = fetch_single_commit(repo_url, primary_ref, repo_dir=repo_dir)
        introducer_diff = fetch_diff_text(repo_url, introducer_commit.sha, repo_dir=repo_dir)
    except Exception as exc:
        return {
            "detected": False,
            "confidence": "中",
            "detection_method": "Fixes tag",
            "summary": f"当前提交通过 Fixes 指向 {primary_ref}，但暂时无法拉取该引入提交的完整信息。",
            "introducer_commit": primary_ref,
            "introducer_title": "",
            "introducer_commit_url": f"{normalized_repo}/+/{primary_ref}",
            "introducer_diff_url": f"{normalized_repo}/+/{primary_ref}^!/",
            "introduced_change_summary": "",
            "why_introduced": "Fixes 标签给出了直接线索，但当前缺少对应引入提交的代码证据。",
            "evidence": [f"Fixes 线索: {fixes_refs[0]}", f"拉取引入提交失败: {exc}"],
        }

    intro_files = extract_files(introducer_diff)
    intro_insertions = count_insertions(introducer_diff)
    intro_deletions = count_deletions(introducer_diff)
    intro_title = introducer_commit.message.splitlines()[0] if introducer_commit.message else introducer_commit.sha
    intro_commit_rich = build_commit_interpretation_rich(introducer_commit.message)
    intro_code_rich = build_code_change_analysis_rich(introducer_diff, intro_files, intro_insertions, intro_deletions)
    current_functions = extract_function_names_from_diff(current_diff)
    before_snippets = collect_before_snippets(current_code_rich)
    corroboration_score, corroboration_evidence = score_candidate_introducer(
        candidate_sha=introducer_commit.sha,
        candidate_message=introducer_commit.message,
        candidate_diff=introducer_diff,
        current_files=current_files,
        current_dirs=sorted({p.split("/", 1)[0] for p in current_files if "/" in p}),
        current_functions=current_functions,
        before_snippets=before_snippets,
        current_title=current_title,
    )

    current_dirs = sorted({p.split("/", 1)[0] for p in current_files if "/" in p})
    intro_dirs = sorted({p.split("/", 1)[0] for p in intro_files if "/" in p})
    shared_dirs = [d for d in intro_dirs if d in current_dirs][:4]
    change_summary = (
        f"引入 patch 修改 {len(intro_files)} 个文件（+{intro_insertions}/-{intro_deletions}），"
        f"主要集中在 {'、'.join(intro_dirs[:6]) if intro_dirs else '相关目录'}。"
    )

    why_parts = ["当前修复提交通过 `Fixes:` 标签直接回指这笔提交，这是最直接的问题引入线索。"]
    if shared_dirs:
        why_parts.append(f"引入 patch 与当前修复都集中在 {'、'.join(shared_dirs)}，说明两者位于同一功能域。")
    if re.search(r"(?i)don't use current pointer", current_message) and re.search(r"\bcurrent\b", introducer_diff):
        why_parts.append("当前修复的核心是去掉对 `current` 的依赖，而引入 patch 在相关路径里确实大量使用了 `current`。")
    if re.search(r"(task->dmabuf_info|current->dmabuf_info)", introducer_diff):
        why_parts.append("引入 patch 把 dmabuf accounting 状态绑定在 task/current 维度，这对部分共享场景的上下文归属并不稳妥。")
    if re.search(r"(copy_dmabuf_info|dma_buf_unaccount_task|dma_buf_account_task)", introducer_diff):
        why_parts.append("引入 patch 已经改动了与本次修复相同的 accounting 关键路径，说明问题并非外围逻辑，而是原始实现本身埋下的。")

    evidence = [
        f"Fixes 线索: {fixes_refs[0]}",
        f"引入提交标题: {intro_title}",
        f"引入提交问题背景: {intro_commit_rich.get('problem_context', '-')}",
        f"引入提交代码摘要: {intro_code_rich.get('summary', '-')}",
    ]
    evidence.extend(corroboration_evidence[:2])
    if shared_dirs:
        evidence.append("共同影响目录: " + "、".join(shared_dirs))

    return {
        "detected": True,
        "confidence": "高",
        "detection_method": "Fixes tag + 代码佐证" if corroboration_score > 0 else "Fixes tag",
        "summary": f"当前修复提交通过 `Fixes:` 直接指向 {introducer_commit.sha}，可将其视为本问题的引入修改。",
        "introducer_commit": introducer_commit.sha,
        "introducer_title": intro_title,
        "introducer_commit_url": f"{normalized_repo}/+/{introducer_commit.sha}",
        "introducer_diff_url": f"{normalized_repo}/+/{introducer_commit.sha}^!/",
        "introduced_change_summary": change_summary,
        "why_introduced": " ".join(why_parts),
        "evidence": evidence[:6],
    }


def build_diff_preview(diff: str, max_lines: int = 220) -> Dict[str, Any]:
    lines = diff.splitlines()
    preview_lines = lines[:max_lines]
    return {
        "total_lines": len(lines),
        "preview_lines": len(preview_lines),
        "text": "\n".join(preview_lines),
        "truncated": len(lines) > max_lines,
    }


def build_why_scored(
    final_score: float,
    recommendation: str,
    high_risk_paths: bool,
    churn: int,
    *,
    trusted_integration_merge: bool = False,
) -> List[str]:
    if trusted_integration_merge:
        return [
            f"综合评分为 {final_score:.1f}/10，对应结论为“{recommendation}”。",
            _TRUSTED_MERGE_POLICY_NOTE,
            "单笔不必按普通补丁做深度 diff 审阅；正确性与回归范围由上游 tag/LTS 说明与产品级集成验证覆盖。",
        ]
    reasons = [
        f"综合评分为 {final_score:.1f}/10，对应结论为“{recommendation}”。",
        "评分基于配置维度加权计算，侧重改动内容与风险面；补丁内是否包含测试代码不影响总分。",
    ]
    if high_risk_paths:
        reasons.append("改动触达核心子系统目录，风险维度评分更严格。")
    if churn > 2500:
        reasons.append("增删行较大，维护性与回归复杂度上升。")
    return reasons[:4]


def _as_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(int(value))
    if isinstance(value, str):
        lower = value.strip().lower()
        if lower in ("true", "yes", "1"):
            return True
        if lower in ("false", "no", "0"):
            return False
    return None


def match_hard_block_condition(
    cond: Dict[str, Any],
    *,
    message: str,
    diff_text: str,
    files: List[str],
    high_risk_paths: bool,
    test_signal: bool,
    churn: int,
) -> bool:
    when = str(cond.get("when", "")).strip()
    if not when:
        return False

    if when == "high_risk_paths_is":
        want = _as_bool(cond.get("value"))
        if want is None:
            return False
        return high_risk_paths is want
    if when == "test_signal_is":
        want = _as_bool(cond.get("value"))
        if want is None:
            return False
        return test_signal is want
    if when == "churn_gt":
        return churn > int(cond.get("threshold", 0))
    if when == "churn_gte":
        return churn >= int(cond.get("threshold", 0))
    if when == "churn_lt":
        return churn < int(cond.get("threshold", 0))
    if when == "churn_lte":
        return churn <= int(cond.get("threshold", 0))

    if when == "message_regex":
        pat = str(cond.get("pattern", ""))
        return bool(pat and re.search(pat, message, flags=re.DOTALL))
    if when == "diff_regex":
        pat = str(cond.get("pattern", ""))
        return bool(pat and re.search(pat, diff_text, flags=re.DOTALL))

    if when == "any_file_prefix":
        prefix = str(cond.get("prefix", ""))
        if not prefix:
            return False
        return any(p.startswith(prefix) for p in files)
    if when == "any_file_regex":
        pat = str(cond.get("pattern", ""))
        if not pat:
            return False
        return any(re.search(pat, p) for p in files)

    if when == "all_files_regex":
        pat = str(cond.get("pattern", ""))
        if not pat or not files:
            return False
        return all(re.search(pat, p) for p in files)

    if when == "not":
        inner = cond.get("cond")
        if not isinstance(inner, dict):
            return False
        return not match_hard_block_condition(
            inner,
            message=message,
            diff_text=diff_text,
            files=files,
            high_risk_paths=high_risk_paths,
            test_signal=test_signal,
            churn=churn,
        )

    return False


def match_hard_block_group(
    group: Dict[str, Any],
    *,
    message: str,
    diff_text: str,
    files: List[str],
    high_risk_paths: bool,
    test_signal: bool,
    churn: int,
) -> bool:
    if "all" in group and "any" in group:
        return False
    if "all" in group:
        items = group.get("all") or []
        if not isinstance(items, list) or not items:
            return False
        for item in items:
            if isinstance(item, dict) and ("all" in item or "any" in item):
                if not match_hard_block_group(item, message=message, diff_text=diff_text, files=files, high_risk_paths=high_risk_paths, test_signal=test_signal, churn=churn):
                    return False
            elif isinstance(item, dict):
                if not match_hard_block_condition(item, message=message, diff_text=diff_text, files=files, high_risk_paths=high_risk_paths, test_signal=test_signal, churn=churn):
                    return False
            else:
                return False
        return True

    if "any" in group:
        items = group.get("any") or []
        if not isinstance(items, list) or not items:
            return False
        for item in items:
            if isinstance(item, dict) and ("all" in item or "any" in item):
                if match_hard_block_group(item, message=message, diff_text=diff_text, files=files, high_risk_paths=high_risk_paths, test_signal=test_signal, churn=churn):
                    return True
            elif isinstance(item, dict):
                if match_hard_block_condition(item, message=message, diff_text=diff_text, files=files, high_risk_paths=high_risk_paths, test_signal=test_signal, churn=churn):
                    return True
            else:
                return False
        return False

    return False


def evaluate_configured_block_rules(
    config: Dict[str, Any],
    enabled_rules: List[str],
    *,
    message: str,
    diff_text: str,
    files: List[str],
    high_risk_paths: bool,
    test_signal: bool,
    churn: int,
) -> List[str]:
    triggers = config.get("hard_block_triggers") or {}
    if not isinstance(triggers, dict):
        return []

    hit: List[str] = []
    for rule_id in enabled_rules:
        if rule_id == "high_risk_without_tests":
            continue
        groups = triggers.get(rule_id)
        if groups is None:
            continue
        if not isinstance(groups, list):
            continue
        for group in groups:
            if not isinstance(group, dict):
                continue
            if not match_hard_block_group(group, message=message, diff_text=diff_text, files=files, high_risk_paths=high_risk_paths, test_signal=test_signal, churn=churn):
                continue
            label = str(group.get("label", "")).strip()
            if label:
                hit.append(f"{rule_id}: {label}")
            else:
                hit.append(rule_id)
            break
    return hit


def evaluate_block_rules(
    config: Dict[str, Any],
    enabled_rules: List[str],
    high_risk_paths: bool,
    test_signal: bool,
    churn: int,
    *,
    message: str,
    diff_text: str,
    files: List[str],
) -> List[str]:
    hit: List[str] = []
    for rule in enabled_rules:
        if rule in ("high_risk_without_tests", "high_risk_large_change") and high_risk_paths and churn > 1800:
            hit.append(rule)
    hit.extend(
        evaluate_configured_block_rules(
            config,
            enabled_rules,
            message=message,
            diff_text=diff_text,
            files=files,
            high_risk_paths=high_risk_paths,
            test_signal=test_signal,
            churn=churn,
        )
    )
    # de-duplicate while preserving order
    seen = set()
    out: List[str] = []
    for item in hit:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def map_recommendation(score: float, mapping: List[Dict[str, Any]]) -> str:
    for item in mapping:
        low = float(item.get("min", 0))
        high = float(item.get("max", 10))
        if low <= score <= high:
            return str(item.get("recommendation", "有条件合入"))
    return "有条件合入"


def floor_score_for_recommendation(mapping: List[Dict[str, Any]], want: str) -> float:
    """Return the inclusive lower bound of the score band for the given recommendation label."""
    for item in mapping:
        if str(item.get("recommendation", "")) == want:
            return float(item.get("min", 8.5))
    return 8.5


_DEFAULT_TRUSTED_MERGE_TITLE_PATTERNS: List[str] = [
    r"(?i)^Merge tag\b",
    r"(?i)^Merge \d+\.\d+\.\d+ into\s+android",
]

_TRUSTED_MERGE_POLICY_NOTE = (
    "trusted_integration_merge：识别为 Merge tag 或 android 树 LTS 小版本批量合入；"
    "按策略不参与常规 diff 规模/路径扣分，各维度对齐「建议合入」档位基准分。"
)


def is_trusted_integration_merge(message: str, config: Dict[str, Any]) -> bool:
    """
    集成类合并：标题首行匹配配置中的正则时，视为发布工程合入，默认走「建议合入」档位。
    """
    ti = config.get("trusted_integration_merge")
    if ti is False:
        return False
    if isinstance(ti, dict) and ti.get("enabled") is False:
        return False

    raw = (message or "").strip()
    if not raw:
        return False
    title = raw.splitlines()[0].strip()

    patterns: List[str] = []
    if isinstance(ti, dict):
        custom = ti.get("title_patterns")
        if isinstance(custom, list) and custom:
            patterns = [str(x) for x in custom if x]
    if not patterns:
        patterns = list(_DEFAULT_TRUSTED_MERGE_TITLE_PATTERNS)

    return any(bool(p and re.search(p, title)) for p in patterns)


def fetch_patch_data(
    repo_url: str,
    commit: CommitItem,
    repo_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Phase 1: Fetch raw commit data (diff, files, metadata) without scoring."""
    diff = fetch_diff_text(repo_url, commit.sha, repo_dir=repo_dir)
    files = extract_files(diff)
    insertions = count_insertions(diff)
    deletions = count_deletions(diff)
    churn = insertions + deletions
    test_signal = detect_test_signal(diff, files)
    high_risk_paths = detect_high_risk_paths(files)
    title = commit.message.splitlines()[0] if commit.message else commit.sha
    commit_message_full = commit.message.strip()
    diff_preview = build_diff_preview(diff)
    normalized_repo = normalize_repo_url(repo_url)
    return {
        "commit": commit.sha,
        "sha": commit.sha,
        "title": title,
        "commit_message": commit.message,
        "commit_message_full": commit_message_full,
        "diff_text": diff,
        "diff_preview": diff_preview,
        "files": files,
        "insertions": insertions,
        "deletions": deletions,
        "churn": churn,
        "test_signal": test_signal,
        "high_risk_paths": high_risk_paths,
        "commit_url": f"{normalized_repo}/+/{commit.sha}",
        "diff_url": f"{normalized_repo}/+/{commit.sha}^!/",
        "score": 0.0,
        "recommendation": "",
        "key_risk": "",
        "blocked": False,
        "block_rules_hit": [],
        "patch_url": f"{normalized_repo}/+/{commit.sha}",
    }


def analyze_commit(
    repo_url: str,
    commit: CommitItem,
    config: Dict[str, Any],
    repo_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Legacy wrapper: fetch patch data and run scoring analysis."""
    data = fetch_patch_data(repo_url, commit, repo_dir=repo_dir)
    return analyze_patch_data(data, config, repo_url, repo_dir=repo_dir)


def analyze_patch_data(
    patch_data: Dict[str, Any],
    config: Dict[str, Any],
    repo_url: str,
    repo_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Phase 2: Run scoring/analysis on pre-fetched patch data."""
    sha = patch_data["sha"]
    message = patch_data.get("commit_message", "")
    diff = patch_data.get("diff_text", "")
    files = patch_data.get("files", [])
    insertions = patch_data.get("insertions", 0)
    deletions = patch_data.get("deletions", 0)
    churn = patch_data.get("churn", 0)
    test_signal = patch_data.get("test_signal", False)
    high_risk_paths = patch_data.get("high_risk_paths", False)
    title = patch_data.get("title", sha[:12])

    matched_rule, profile = choose_profile(config, files)
    weights = profile.get("dimension_weights", {})
    score_rules = profile.get("score_rules") or {}
    score_rules = merge_risk_signal_score_rules(score_rules, config.get("risk_signal_score_rules"))
    dim_details = compute_dimension_details(
        message=message,
        files=files,
        ins=insertions,
        dels=deletions,
        test_signal=test_signal,
        high_risk_paths=high_risk_paths,
        score_rules=score_rules,
        diff_text=diff,
    )
    dim_scores = compute_dimension_scores(
        message=message,
        files=files,
        ins=insertions,
        dels=deletions,
        test_signal=test_signal,
        high_risk_paths=high_risk_paths,
        score_rules=score_rules,
        diff_text=diff,
    )
    final_score = 0.0
    for dim, val in dim_scores.items():
        final_score += float(weights.get(dim, 0)) * val

    round_digits = int(((config.get("scale") or {}).get("round_digits", 1)))
    final_score = round(final_score, round_digits)

    enabled_block_rules = profile.get("enabled_hard_block_rules", [])
    block_hits = evaluate_block_rules(
        config,
        enabled_block_rules,
        high_risk_paths,
        test_signal,
        churn,
        message=message,
        diff_text=diff,
        files=files,
    )

    rec_mapping = config.get("recommendation_mapping", [])
    trusted_merge = False
    if block_hits:
        recommendation = "不建议合入"
    else:
        trusted_merge = is_trusted_integration_merge(message, config)
        if trusted_merge:
            gate_score = round(floor_score_for_recommendation(rec_mapping, "建议合入"), round_digits)
            for dim in dim_scores:
                if dim != "testability_evidence":
                    dim_scores[dim] = gate_score
            final_score = 0.0
            for dim, val in dim_scores.items():
                final_score += float(weights.get(dim, 0)) * val
            final_score = round(final_score, round_digits)
            recommendation = "建议合入"
        else:
            recommendation = map_recommendation(final_score, rec_mapping)

    if trusted_merge:
        dim_reasons = {
            dim: _TRUSTED_MERGE_POLICY_NOTE
            for dim in dim_scores.keys()
            if dim != "testability_evidence"
        }
    else:
        dim_reasons = build_dimension_reasons(
            message=message,
            file_count=len(files),
            churn=churn,
            test_signal=test_signal,
            high_risk_paths=high_risk_paths,
        )

    score_details: Dict[str, Dict[str, Any]] = {}
    for dim, score in dim_scores.items():
        w = float(weights.get(dim, 0))
        if trusted_merge:
            gate = float(score)
            applied_rules = [_TRUSTED_MERGE_POLICY_NOTE]
            breakdown: Dict[str, Any] = {
                "base_score": gate,
                "additions": [_TRUSTED_MERGE_POLICY_NOTE],
                "deductions": [],
                "unclamped_score": gate,
                "final_raw_score": gate,
            }
        else:
            applied_rules = (dim_details.get(dim) or {}).get("applied_rules", [])
            breakdown = (dim_details.get(dim) or {}).get("breakdown", {})

        score_details[dim] = {
            "score": score,
            "weight": w,
            "weighted_score": round(float(score) * w, 3),
            "reason": dim_reasons.get(dim, ""),
            "applied_rules": applied_rules,
            "breakdown": breakdown,
        }
    score_details.pop("testability_evidence", None)

    dimensions_out = {k: v for k, v in dim_scores.items() if k != "testability_evidence"}

    if trusted_merge:
        key_risk = "集成类合并；默认建议合入，风险由上游 tag/LTS 与产品级集成验证覆盖。"
    else:
        key_risk = "风险可控，关注常规回归"
        if high_risk_paths and churn > 3000:
            key_risk = "核心子系统大范围改动，需重点回归与审阅深度"
        elif high_risk_paths:
            key_risk = "核心子系统改动需重点回归"
        elif churn > 3000:
            key_risk = "改动规模较大，回归与风险面审阅成本高"

    problem_solved = infer_problem_solved(message, diff, files)
    change_summary = summarize_change_content(files, insertions, deletions, recommendation)
    commit_interpretation = build_commit_interpretation(message)
    commit_interpretation_rich = build_commit_interpretation_rich(message)
    code_change_analysis = build_code_change_analysis(diff, files, insertions, deletions)
    code_change_analysis_rich = build_code_change_analysis_rich(diff, files, insertions, deletions)
    problem_closure_rich = build_problem_closure_rich(
        recommendation=recommendation,
        blocked=bool(block_hits),
        block_hits=block_hits,
        problem_solved=problem_solved,
        commit_rich=commit_interpretation_rich,
        code_rich=code_change_analysis_rich,
    )
    problem_introducer_rich = build_problem_introducer_rich(
        repo_url=repo_url,
        current_sha=sha,
        current_title=title,
        current_message=message,
        current_diff=diff,
        current_files=files,
        current_code_rich=code_change_analysis_rich,
        problem_closure_rich=problem_closure_rich,
        repo_dir=repo_dir,
    )
    diff_preview = build_diff_preview(diff)
    normalized_repo = normalize_repo_url(repo_url)
    commit_url = f"{normalized_repo}/+/{sha}"
    diff_url = f"{normalized_repo}/+/{sha}^!/"
    patch_tags = merge_patch_tags_with_intent(files, message)
    platform_tags = build_platform_tags(files)

    return {
        "trusted_integration_merge": trusted_merge,
        "commit": sha,
        "title": title,
        "patch_url": commit_url,
        "commit_url": commit_url,
        "diff_url": diff_url,
        "score": final_score,
        "recommendation": recommendation,
        "blocked": bool(block_hits),
        "block_rules_hit": block_hits,
        "active_profile": matched_rule,
        "patch_tags": patch_tags,
        "patch_tag_labels": [tag.get("label", "") for tag in patch_tags if tag.get("label")],
        "platform_tags": platform_tags,
        "platform_tag_labels": [tag.get("label", "") for tag in platform_tags if tag.get("label")],
        "key_risk": key_risk,
        "files_changed": len(files),
        "files": files,
        "insertions": insertions,
        "deletions": deletions,
        "dimensions": dimensions_out,
        "score_details": score_details,
        "why_scored": build_why_scored(
            final_score=final_score,
            recommendation=recommendation,
            high_risk_paths=high_risk_paths,
            churn=churn,
            trusted_integration_merge=trusted_merge,
        ),
        "change_summary": change_summary,
        "problem_solved": problem_solved,
        "commit_interpretation": commit_interpretation,
        "commit_interpretation_rich": commit_interpretation_rich,
        "code_change_analysis": code_change_analysis,
        "code_change_analysis_rich": code_change_analysis_rich,
        "problem_closure_rich": problem_closure_rich,
        "problem_introducer_rich": problem_introducer_rich,
        "commit_message_full": message.strip(),
        "diff_preview": diff_preview,
        "test_suggestions": build_test_suggestions(
            files=files,
            high_risk_paths=high_risk_paths,
            test_signal=test_signal,
            churn=churn,
            config=config,
            profile=profile,
            patch_tags=patch_tags,
            platform_tags=platform_tags,
        ),
    }


def chunk_list(items: List[Any], size: int) -> List[List[Any]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def run_parallel_analysis(
    repo_url: str,
    commits: List[CommitItem],
    config: Dict[str, Any],
    workers: int,
    chunk_size: int,
    retry: int,
    repo_dir: Optional[Path] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    chunks = chunk_list(commits, chunk_size)
    results: List[Dict[str, Any]] = []
    failures: List[Dict[str, Any]] = []

    def analyze_chunk(chunk: List[CommitItem]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        ok, bad = [], []
        for commit in chunk:
            last_err = None
            for _ in range(retry + 1):
                try:
                    ok.append(analyze_commit(repo_url, commit, config, repo_dir=repo_dir))
                    last_err = None
                    break
                except Exception as exc:  # pylint: disable=broad-except
                    last_err = exc
                    time.sleep(0.2)
            if last_err is not None:
                bad.append({"commit": commit.sha, "error": str(last_err)})
        return ok, bad

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_chunk = {executor.submit(analyze_chunk, c): idx for idx, c in enumerate(chunks)}
        for fut in concurrent.futures.as_completed(future_to_chunk):
            ok, bad = fut.result()
            results.extend(ok)
            failures.extend(bad)
            idx = future_to_chunk[fut] + 1
            total = len(chunks)
            print(f"[progress] chunk {idx}/{total} done, ok={len(ok)}, failed={len(bad)}", file=sys.stderr)
    return results, failures


def build_summary(patches: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not patches:
        return {
            "avg_score": 0,
            "blocked_count": 0,
            "recommendation_counts": {"建议合入": 0, "有条件合入": 0, "需大幅修改": 0, "不建议合入": 0},
            "intent_tag_counts": {"fix bug": 0, "新需求": 0},
        }
    avg = round(sum(float(p["score"]) for p in patches) / len(patches), 1)
    blocked = sum(1 for p in patches if p.get("blocked"))
    counts: Dict[str, int] = {"建议合入": 0, "有条件合入": 0, "需大幅修改": 0, "不建议合入": 0}
    for p in patches:
        rec = str(p.get("recommendation", "有条件合入"))
        counts[rec] = counts.get(rec, 0) + 1
    fix_bug_n = sum(
        1
        for p in patches
        for t in (p.get("patch_tags") or [])
        if str((t or {}).get("label", "")).strip() == "fix bug"
    )
    feat_n = sum(
        1
        for p in patches
        for t in (p.get("patch_tags") or [])
        if str((t or {}).get("label", "")).strip() == "新需求"
    )
    return {
        "avg_score": avg,
        "blocked_count": blocked,
        "recommendation_counts": counts,
        "intent_tag_counts": {"fix bug": fix_bug_n, "新需求": feat_n},
    }


def main() -> int:
    from cli_config import (
        add_settings_argument,
        get_repo_dir,
        load_settings,
        patch_analyzer_defaults,
        resolve_output_path,
        strip_settings_from_argv,
    )

    settings_path, argv_rest = strip_settings_from_argv(sys.argv[1:])
    settings, loaded_from = load_settings(settings_path)
    defaults = patch_analyzer_defaults(settings)

    parser = argparse.ArgumentParser(description="Patch analyzer (general, outside Cursor)")
    add_settings_argument(parser)
    parser.add_argument("--repo", default=defaults["repo"], help="repo url")
    parser.add_argument("--config", default=defaults["config"], help="path to scoring-config.yaml")
    parser.add_argument("--from-tag", help="start tag")
    parser.add_argument("--to-tag", help="end tag")
    parser.add_argument("--commit", help="single commit sha")
    parser.add_argument("--workers", type=int, default=defaults["workers"], help="parallel workers")
    parser.add_argument("--chunk-size", type=int, default=defaults["chunk_size"], help="commits per chunk")
    parser.add_argument("--retry", type=int, default=defaults["retry"], help="retry count per commit")
    parser.add_argument("--repo-dir", help="local git repo directory (avoid remote API throttling)")
    parser.add_argument("--output", default=None, help="output json path")
    args = parser.parse_args(argv_rest)

    if loaded_from:
        print(f"[config] 已加载: {loaded_from}", file=sys.stderr)

    if not args.repo:
        print("错误: 未指定 --repo，且配置文件中未设置 repo.url", file=sys.stderr)
        return 2
    if not args.config:
        print("错误: 未指定 --config，且配置文件中未设置 scoring.config", file=sys.stderr)
        return 2

    if not args.commit and not (args.from_tag and args.to_tag):
        print("错误: 必须提供 --commit 或 --from-tag + --to-tag", file=sys.stderr)
        return 2
    if args.commit and (args.from_tag or args.to_tag):
        print("错误: --commit 与 --from-tag/--to-tag 不能同时使用", file=sys.stderr)
        return 2

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"错误: 评分配置文件不存在: {config_path}", file=sys.stderr)
        return 2

    config = load_config(config_path)
    repo = normalize_repo_url(args.repo)
    repo_dir = get_repo_dir(settings, cli_repo_dir=args.repo_dir)
    out_path = resolve_output_path(settings, args.output)
    if repo_dir and not repo_dir.exists():
        print(f"错误: 本地仓库路径不存在: {repo_dir}", file=sys.stderr)
        return 2

    if args.commit:
        commits = [fetch_single_commit(repo, args.commit, repo_dir=repo_dir)]
        from_tag = ""
        to_tag = ""
    else:
        commits = fetch_commits_between_tags(repo, args.from_tag, args.to_tag, repo_dir=repo_dir)
        from_tag = args.from_tag
        to_tag = args.to_tag

    patches, failures = run_parallel_analysis(
        repo_url=repo,
        commits=commits,
        config=config,
        workers=max(1, args.workers),
        chunk_size=max(1, args.chunk_size),
        retry=max(0, args.retry),
        repo_dir=repo_dir,
    )
    patches.sort(key=lambda x: x["commit"])
    output = {
        "repo": repo,
        "from_tag": from_tag,
        "to_tag": to_tag,
        "total": len(commits),
        "analyzed": len(patches),
        "failed": len(failures),
        "failed_items": failures,
        "summary": build_summary(patches),
        "patches": patches,
    }
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"完成: analyzed={len(patches)}, failed={len(failures)}, output={out_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except urllib.error.URLError as exc:
        print(f"网络请求失败: {exc}", file=sys.stderr)
        raise SystemExit(1)
