"""开发模块分类 — dev_modules.txt 路径规则 + LLM 语义判断。

分类优先级：
1. 非代码类 patch → 「其他」
2. 已 LLM 分析的 patch → 采用 LLM 返回的 dev_module（结合路径与 diff 语义）
3. 变更文件路径 + 最长路径模式匹配（dev_modules.txt，供未 LLM 分析或规则免 LLM 时使用）
4. LLM 建议兜底（合法模块名）
5. 代码类仍无法匹配 → 「驱动框架」
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from web_app.app_paths import dev_modules_path

_DEV_MODULES_FILE = dev_modules_path()

_OTHER_ALLOWED_PATTERNS = [
    "tools/", "scripts/", "makefile", "documentation/",
    "android/", "selftests/",
]

_cache: Optional[Dict[str, Any]] = None


def invalidate_dev_modules_cache() -> None:
    global _cache
    _cache = None


def load_dev_modules() -> Dict[str, Any]:
    """加载 dev_modules.txt → {rules, names, descriptions, rules_by_length}."""
    global _cache
    if _cache is not None:
        return _cache

    rules: List[Tuple[str, str]] = []
    names: List[str] = []
    descriptions: Dict[str, str] = {}

    try:
        text = _DEV_MODULES_FILE.read_text(encoding="utf-8")
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 3:
                continue
            name, patterns_str, desc = parts[0], parts[1], parts[2]
            if name not in descriptions:
                names.append(name)
                descriptions[name] = desc
            for pat in patterns_str.split(","):
                pat = pat.strip()
                if pat:
                    rules.append((pat, name))
    except FileNotFoundError:
        print(f"[WARN] dev_modules.txt not found: {_DEV_MODULES_FILE}", flush=True)

    rules_by_length = sorted(rules, key=lambda x: len(x[0]), reverse=True)
    _cache = {
        "rules": rules,
        "rules_by_length": rules_by_length,
        "names": names,
        "descriptions": descriptions,
    }
    return _cache


def get_dev_module_names() -> List[str]:
    return list(load_dev_modules()["names"])


def get_dev_module_descriptions() -> Dict[str, str]:
    return dict(load_dev_modules()["descriptions"])


def get_official_module_set() -> Set[str]:
    return set(get_dev_module_names()) | {"其他"}


def normalize_dev_module_name(name: str) -> str:
    """规范化模块名，必须在 dev_modules.txt 定义列表中才保留。"""
    name = (name or "").strip()
    if not name:
        return ""
    official = get_official_module_set()
    if name in official:
        return name
    # 模糊匹配：去掉空格后比对
    compact = name.replace(" ", "")
    for n in get_dev_module_names():
        if n.replace(" ", "") == compact:
            return n
    return ""


def _normalize_path(path: str) -> str:
    return path.strip().replace("\\", "/").lstrip("./").lower()


def _path_matches_pattern(path: str, pattern: str) -> bool:
    """路径是否命中 dev_modules.txt 中的模式。

    对不含结尾 ``/`` 的多段路径模式（如 ``include/linux/mm``），按路径边界匹配，
    避免 ``include/linux/mm`` 误命中 ``include/linux/mmc/...``。
    """
    path = _normalize_path(path)
    pat = pattern.strip().lower()
    if not pat or not path:
        return False
    # 带结尾 / 的模式：作为目录前缀 / 路径片段匹配
    if pat.endswith("/"):
        return f"/{pat}" in f"/{path}/" or path.startswith(pat)
    if "/" in pat:
        return (
            path == pat
            or path.startswith(pat + "/")
            or path.startswith(pat + ".")
            or f"/{pat}/" in f"/{path}/"
            or f"/{pat}." in f"/{path}"
        )
    # 单词模式：路径段边界匹配，避免短词误伤
    return (
        f"/{pat}/" in f"/{path}/"
        or path.startswith(pat + "/")
        or path.endswith("/" + pat)
        or path == pat
        or f"/{pat}." in f"/{path}"
    )


def _match_file_to_module(file_path: str, rules_by_length: List[Tuple[str, str]]) -> Optional[str]:
    """单文件最长模式匹配 → 模块名。"""
    for pattern, module in rules_by_length:
        if _path_matches_pattern(file_path, pattern):
            return module
    return None


def _is_non_code_patch(files: List[str], title: str, combined_lower: str) -> bool:
    if title.startswith("Linux ") or title.startswith("Merge "):
        return True
    for f in files:
        fp = _normalize_path(f)
        for nc in _OTHER_ALLOWED_PATTERNS:
            if fp.startswith(nc) or f"/{nc}" in f"/{fp}/":
                return True
    for nc in _OTHER_ALLOWED_PATTERNS:
        if nc in combined_lower and not any(
            _normalize_path(f).startswith(("drivers/", "kernel/", "arch/", "fs/", "net/", "mm/"))
            for f in files
        ):
            return True
    return False


def _extract_diff_text(patch_data: Dict[str, Any]) -> str:
    diff_raw = patch_data.get("diff_preview", {})
    if isinstance(diff_raw, dict):
        return diff_raw.get("text", "") or ""
    if isinstance(diff_raw, str):
        return diff_raw
    return ""


def _collect_diff_paths(diff_text: str, limit: int = 200) -> List[str]:
    paths: List[str] = []
    for line in diff_text.splitlines()[:limit]:
        if line.startswith("+++ b/") or line.startswith("--- a/"):
            p = line.split("\t", 1)[0][6:].strip()
            if p and p != "/dev/null":
                paths.append(p)
    return paths


def _classify_by_path_votes(
    files: List[str],
    diff_text: str,
    rules_by_length: List[Tuple[str, str]],
) -> Optional[str]:
    """按文件路径最长模式匹配，多文件多数决。"""
    candidates: List[str] = list(files)
    if not candidates:
        candidates = _collect_diff_paths(diff_text)
    if not candidates:
        return None

    votes: Dict[str, int] = defaultdict(int)
    weight: Dict[str, int] = defaultdict(int)
    for fp in candidates:
        mod = _match_file_to_module(fp, rules_by_length)
        if mod:
            votes[mod] += 1
            weight[mod] += max(len(fp), 1)
    if not votes:
        return None
    return max(votes.keys(), key=lambda m: (votes[m], weight[m]))


def path_hint_for_patch(patch_data: Dict[str, Any]) -> str:
    """路径规则给出的参考模块（供 LLM prompt 参考，不作最终裁决）。"""
    cfg = load_dev_modules()
    files: List[str] = list(patch_data.get("files") or [])
    diff_text = _extract_diff_text(patch_data)
    return _classify_by_path_votes(files, diff_text, cfg["rules_by_length"]) or ""


def classify_patch_dev_module(
    patch_data: Dict[str, Any],
    llm_suggestion: str = "",
) -> str:
    """对单笔 patch 分类，返回 dev_modules.txt 中的模块名。"""
    cfg = load_dev_modules()
    rules_by_length: List[Tuple[str, str]] = cfg["rules_by_length"]
    official = get_official_module_set()

    files: List[str] = list(patch_data.get("files") or [])
    title = (patch_data.get("title") or "").strip()
    diff_text = _extract_diff_text(patch_data)
    combined_lower = (" ".join(files) + " " + diff_text[:3000]).lower()

    # ── 1. 非代码类 → 其他 ──
    if _is_non_code_patch(files, title, combined_lower):
        return "其他"

    llm_mod = normalize_dev_module_name(
        llm_suggestion or str(patch_data.get("dev_module") or "")
    )
    path_mod = _classify_by_path_votes(files, diff_text, rules_by_length)
    llm_analyzed = bool(patch_data.get("llm_analyzed"))
    rule_based = bool(patch_data.get("rule_based"))

    # ── 2. 已 LLM 分析：以模型语义判断为准 ──
    if llm_analyzed and not rule_based and llm_mod and llm_mod != "其他":
        return llm_mod

    # ── 3. 路径规则（未 LLM 分析 / 规则免 LLM / LLM 未给出合法模块） ──
    if path_mod:
        return path_mod

    # ── 4. LLM 建议兜底 ──
    if llm_mod and llm_mod != "其他":
        return llm_mod

    # ── 5. 代码类兜底：驱动框架 ──
    if "驱动框架" in official:
        return "驱动框架"
    return "其他"


def classify_and_assign_patch(
    patch_data: Dict[str, Any],
    llm_suggestion: str = "",
) -> str:
    """分类并写回 patch_data['dev_module']。"""
    mod = classify_patch_dev_module(patch_data, llm_suggestion=llm_suggestion)
    patch_data["dev_module"] = mod
    return mod


def group_patches_by_official_module(
    patches: List[Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    """按 dev_modules.txt 重新分类并分组。"""
    groups: Dict[str, List[Dict[str, Any]]] = {name: [] for name in get_dev_module_names()}
    groups["其他"] = []

    for p in patches:
        llm_hint = p.get("dev_module", "")
        mod = classify_patch_dev_module(p, llm_suggestion=llm_hint)
        p["dev_module"] = mod
        if mod not in groups:
            groups[mod] = []
        groups[mod].append(p)

    return {k: v for k, v in groups.items() if v}


def sort_modules_by_definition(module_items: List[Tuple[str, Any]]) -> List[Tuple[str, Any]]:
    """按 dev_modules.txt 中的模块顺序排序，同顺序内按 patch 数降序。"""
    order = {name: i for i, name in enumerate(get_dev_module_names())}
    other_rank = len(order) + 1

    def sort_key(item: Tuple[str, Any]) -> Tuple[int, int]:
        name, payload = item
        count = 0
        if isinstance(payload, list):
            count = len(payload)
        elif isinstance(payload, dict):
            stats = payload.get("stats") or {}
            count = stats.get("patch_count", 0)
        rank = order.get(name, other_rank)
        return (rank, -count)

    return sorted(module_items, key=sort_key)
