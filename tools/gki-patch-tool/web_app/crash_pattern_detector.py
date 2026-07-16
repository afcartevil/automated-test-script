#!/usr/bin/env python3
"""Crash pattern detector - static rule engine for identifying crash-inducing code changes.

Analyzes patch diffs against known patterns that commonly introduce kernel crashes
(null pointer dereference, use-after-free, lock imbalance, etc.).
"""
import re
from typing import Any, Dict, List, Optional


# ── Pattern definitions ──────────────────────────────────
# Each pattern: (id, label, severity, description, regex_list)
# severity: "高" / "中" / "低"
# regex_list: list of (regex_pattern, is_deleted_line) tuples
#   is_deleted_line=True means we look for this pattern in removed lines (lines starting with -)
#   is_deleted_line=False means we look for this pattern in added lines (lines starting with +)

CRASH_PATTERNS: List[Dict[str, Any]] = [
    {
        "id": "null_check_removed",
        "label": "移除空指针检查",
        "severity": "高",
        "description": "删除了对指针/引用的空值检查，可能导致空指针解引用",
        "deleted_patterns": [
            r'if\s*\(\s*!\s*\w+\s*\)',           # if (!ptr)
            r'if\s*\(\s*\w+\s*==\s*NULL\s*\)',     # if (ptr == NULL)
            r'if\s*\(\s*NULL\s*==\s*\w+\s*\)',     # if (NULL == ptr)
            r'if\s*\(\s*\w+\s*!=\s*NULL\s*\)',     # if (ptr != NULL)
            r'if\s*\(\s*\w+\s*\)',                 # if (ptr) - truthy check
            r'if\s*\(\s*IS_ERR\s*\(',              # if (IS_ERR(...))
        ],
    },
    {
        "id": "error_handling_removed",
        "label": "移除错误处理",
        "severity": "中",
        "description": "删除了错误返回值检查，异常路径可能触发崩溃",
        "deleted_patterns": [
            r'if\s*\(\s*ret\s*[<>=!]',            # if (ret < 0) / if (ret != 0)
            r'if\s*\(\s*err\s*[<>=!]',            # if (err < 0)
            r'if\s*\(\s*IS_ERR\s*\(',             # if (IS_ERR(...))
            r'if\s*\(\s*IS_ERR_OR_NULL\s*\(',     # if (IS_ERR_OR_NULL(...))
            r'goto\s+err',                         # goto err_out
            r'return\s+-E',                        # return -EINVAL etc
        ],
    },
    {
        "id": "lock_imbalance",
        "label": "锁操作不对称",
        "severity": "高",
        "description": "新增或移除锁操作可能导致死锁或未加锁访问",
        "added_patterns": [
            r'spin_lock\s*\(',                     # spin_lock(
            r'spin_lock_irqsave\s*\(',             # spin_lock_irqsave(
            r'mutex_lock\s*\(',                    # mutex_lock(
            r'rcu_read_lock\s*\(',                 # rcu_read_lock(
            r'raw_spin_lock\s*\(',                 # raw_spin_lock(
        ],
        "deleted_patterns": [
            r'spin_unlock\s*\(',                   # spin_unlock(
            r'spin_unlock_irqrestore\s*\(',        # spin_unlock_irqrestore(
            r'mutex_unlock\s*\(',                  # mutex_unlock(
            r'rcu_read_unlock\s*\(',               # rcu_read_unlock(
            r'raw_spin_unlock\s*\(',               # raw_spin_unlock(
        ],
    },
    {
        "id": "irq_context_alloc",
        "label": "中断上下文内存分配",
        "severity": "高",
        "description": "在中断/软中断路径中使用 GFP_KERNEL 分配可能导致死机",
        "added_patterns": [
            r'kmalloc\s*\([^)]*GFP_KERNEL',       # kmalloc(..., GFP_KERNEL)
            r'kzalloc\s*\([^)]*GFP_KERNEL',       # kzalloc(..., GFP_KERNEL)
            r'kcalloc\s*\([^)]*GFP_KERNEL',       # kcalloc(..., GFP_KERNEL)
            r'vmalloc\s*\(',                       # vmalloc (not allowed in atomic)
            r'kvmalloc\s*\([^)]*GFP_KERNEL',      # kvmalloc(..., GFP_KERNEL)
        ],
    },
    {
        "id": "uaf_risk",
        "label": "Use-After-Free 风险",
        "severity": "高",
        "description": "释放后仍可能使用已释放的内存",
        "deleted_patterns": [
            r'kfree\s*\(',                         # kfree(
            r'kfree_rcu\s*\(',                     # kfree_rcu(
            r'put_device\s*\(',                    # put_device(
            r'kobject_put\s*\(',                   # kobject_put(
        ],
    },
    {
        "id": "barrier_removed",
        "label": "移除内存屏障",
        "severity": "中",
        "description": "删除内存屏障可能导致多核环境下的竞态条件",
        "deleted_patterns": [
            r'smp_mb\s*\(',                        # smp_mb()
            r'smp_rmb\s*\(',                       # smp_rmb()
            r'smp_wmb\s*\(',                       # smp_wmb()
            r'mb\s*\(',                            # mb()
            r'rmb\s*\(',                           # rmb()
            r'wmb\s*\(',                           # wmb()
            r'barrier\s*\(',                       # barrier()
            r'read_barrier_depends\s*\(',          # read_barrier_depends()
        ],
    },
    {
        "id": "refcount_removed",
        "label": "移除引用计数操作",
        "severity": "中",
        "description": "删除引用计数操作可能导致对象过早释放",
        "deleted_patterns": [
            r'get_device\s*\(',                    # get_device(
            r'kobject_get\s*\(',                   # kobject_get(
            r'kref_get\s*\(',                      # kref_get(
            r'refcount_inc\s*\(',                  # refcount_inc(
            r'atomic_inc\s*\(',                    # atomic_inc(
        ],
    },
    {
        "id": "list_manipulation_unsafe",
        "label": "不安全的链表操作",
        "severity": "中",
        "description": "未加锁或使用非安全版本的链表遍历/操作可能导致竞态",
        "added_patterns": [
            r'list_for_each\b',                    # list_for_each (non-safe version)
            r'list_for_each_entry\b',              # list_for_each_entry (non-safe)
            r'list_del\s*\(',                      # list_del (not list_del_init)
        ],
    },
]


def _extract_diff_lines(diff_text: str) -> tuple:
    """Extract added and deleted lines from a unified diff."""
    added_lines = []
    deleted_lines = []
    for line in diff_text.split("\n"):
        if line.startswith("+") and not line.startswith("+++"):
            added_lines.append(line[1:])
        elif line.startswith("-") and not line.startswith("---"):
            deleted_lines.append(line[1:])
    return added_lines, deleted_lines


def _match_patterns(lines: List[str], patterns: List[str]) -> List[str]:
    """Check if any line matches any pattern. Return list of matched pattern strings."""
    matched = []
    for pattern in patterns:
        regex = re.compile(pattern)
        for line in lines:
            if regex.search(line):
                matched.append(line.strip())
                break  # one match per pattern is enough
    return matched


def detect_crash_patterns(diff_preview: Any) -> List[Dict[str, Any]]:
    """Analyze a patch diff for crash-inducing patterns.

    Args:
        diff_preview: Either a dict with "text" key, or a string containing diff text.

    Returns:
        List of matched pattern dicts with id, label, severity, description, matched_lines.
    """
    if isinstance(diff_preview, dict):
        diff_text = diff_preview.get("text", "")
    else:
        diff_text = str(diff_preview or "")

    if not diff_text:
        return []

    added_lines, deleted_lines = _extract_diff_lines(diff_text)
    results = []

    for pattern_def in CRASH_PATTERNS:
        matched_lines = []

        # Check deleted line patterns
        if "deleted_patterns" in pattern_def and deleted_lines:
            hits = _match_patterns(deleted_lines, pattern_def["deleted_patterns"])
            matched_lines.extend(hits)

        # Check added line patterns
        if "added_patterns" in pattern_def and added_lines:
            hits = _match_patterns(added_lines, pattern_def["added_patterns"])
            matched_lines.extend(hits)

        # Special logic for lock_imbalance: only flag if added != deleted counts
        if pattern_def["id"] == "lock_imbalance" and matched_lines:
            added_locks = len(_match_patterns(added_lines, pattern_def.get("added_patterns", [])))
            deleted_locks = len(_match_patterns(deleted_lines, pattern_def.get("deleted_patterns", [])))
            if added_locks == deleted_locks:
                continue  # balanced, no risk

        if matched_lines:
            results.append({
                "id": pattern_def["id"],
                "label": pattern_def["label"],
                "severity": pattern_def["severity"],
                "description": pattern_def["description"],
                "matched_lines": matched_lines[:5],  # limit to 5 examples
            })

    return results
