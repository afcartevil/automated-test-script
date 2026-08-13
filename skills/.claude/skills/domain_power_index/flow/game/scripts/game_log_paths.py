"""flow/game 统一日志路径：默认使用 mobilelog 下的 APLog 目录。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _setup_utf8_stdio() -> None:
    for name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, name, None)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


FLOW_GAME_ROOT = Path(__file__).resolve().parent.parent
MOBILELOG_DIR = FLOW_GAME_ROOT / "mobilelog"

# 无参数时的默认样例目录（mobilelog 下最新 APLog 优先）
DEFAULT_APLOG_NAME = "APLog_2026_0622_201151__6"

LOG_PATH_HELP = (
    "日志目录，默认 flow/game/mobilelog/<APLog_*>；"
    "省略时使用 mobilelog 下最新或默认 APLog 目录；"
    "也可传 case 根目录（其下有多份 APLog_* 时自动双机对比）"
)

WINDOW_JSON_HELP = (
    "game_time_window.json；默认 <log_path>/analysis/game_time_window.json"
)

_SKIP_LABEL_NAMES = frozenset(
    {
        "mobilelog",
        "aplog",
        "analysis",
        "downloads",
        "temp",
        "log",
        "logs",
        "data",
        "debug",
        "bugreport",
    }
)


def default_aplog_dir() -> Path:
    named = MOBILELOG_DIR / DEFAULT_APLOG_NAME
    if named.is_dir():
        return named
    candidates = sorted(
        (p for p in MOBILELOG_DIR.glob("APLog_*") if p.is_dir()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if candidates:
        return candidates[0]
    return named


def is_aplog_dir(path: Path) -> bool:
    name = path.name
    return path.is_dir() and name.startswith("APLog_")


def discover_aplog_dirs(root: Path, *, max_depth: int = 8) -> list[Path]:
    """在 root 下递归发现 APLog_* 目录（按路径排序，去重）。"""
    root = Path(root).resolve()
    if not root.is_dir():
        return []
    if is_aplog_dir(root):
        return [root]
    found: list[Path] = []
    root_depth = len(root.parts)
    for p in root.rglob("APLog_*"):
        if not p.is_dir():
            continue
        if len(p.parts) - root_depth > max_depth:
            continue
        if is_aplog_dir(p):
            found.append(p.resolve())
    # 稳定排序：按路径，便于 case 下 CN6/X6887 等可预期配对
    found = sorted(set(found), key=lambda x: str(x).lower())
    return found


def infer_device_label(aplog: Path) -> str:
    """从 APLog 上级目录推断机型/项目标签（如 CN6、X6887）。"""
    aplog = Path(aplog).resolve()
    for parent in aplog.parents:
        name = parent.name.strip()
        if not name or name.lower() in _SKIP_LABEL_NAMES:
            continue
        if name.startswith("APLog_"):
            continue
        # 常见：CASE/DEVICE/SN/mobilelog/APLog → DEVICE
        # 或 DEVICE 嵌在 SN 名里：1716...-CN6
        if "-" in name and any(ch.isdigit() for ch in name):
            tail = name.rsplit("-", 1)[-1].strip()
            if tail and not tail.isdigit() and len(tail) <= 24:
                return tail
        if len(name) <= 32 and not name.lower().startswith("aplog"):
            return name
    return aplog.name


def _case_root_for_aplog(aplog: Path) -> Path:
    """猜测 case 根：含多个机型子目录的那一层。"""
    aplog = Path(aplog).resolve()
    # APLog → mobilelog → SN → DEVICE → CASE
    candidates = list(aplog.parents)[:6]
    for parent in candidates:
        siblings = discover_aplog_dirs(parent, max_depth=6)
        if len(siblings) >= 2:
            return parent
    return aplog.parent


def resolve_log_path(log_path: str | None) -> Path:
    if log_path and str(log_path).strip():
        p = Path(log_path).resolve()
        if is_aplog_dir(p):
            return p
        # case / 中间目录：若仅 1 份 APLog 则直接用；多份时仍返回原路径，由 resolve_log_pair 处理
        found = discover_aplog_dirs(p)
        if len(found) == 1:
            return found[0]
        if len(found) >= 2:
            return found[0]
        return p
    return default_aplog_dir().resolve()


def resolve_log_pair(
    log_path: str | None,
    log_compare: str | None = None,
) -> tuple[Path, Path | None, str, str]:
    """解析测试机/对比机 APLog。

    返回 (primary, compare_or_None, primary_label, compare_label)。
    - 显式 --log-compare → 双机
    - 传入 case 根且发现 ≥2 份 APLog → 取前两份
    - 传入单份 APLog 且同 case 下另有一份 → 自动配对
    - 仅一份 → compare=None（不对比）
    """
    compare_arg = (log_compare or "").strip()
    raw = Path(log_path).resolve() if (log_path and str(log_path).strip()) else default_aplog_dir().resolve()

    if compare_arg:
        primary = resolve_log_path(str(raw) if is_aplog_dir(raw) or raw.exists() else log_path)
        compare = resolve_log_path(compare_arg)
        if primary.resolve() == compare.resolve():
            return primary, None, infer_device_label(primary), ""
        return primary, compare, infer_device_label(primary), infer_device_label(compare)

    if is_aplog_dir(raw):
        case_root = _case_root_for_aplog(raw)
        all_logs = discover_aplog_dirs(case_root)
        primary = raw.resolve()
        others = [p for p in all_logs if p.resolve() != primary]
        if not others:
            return primary, None, infer_device_label(primary), ""
        compare = others[0]
        return primary, compare, infer_device_label(primary), infer_device_label(compare)

    # case / 中间目录
    found = discover_aplog_dirs(raw)
    if not found:
        # 回退到默认单日志
        primary = resolve_log_path(str(raw) if raw.exists() else None)
        return primary, None, infer_device_label(primary), ""
    if len(found) == 1:
        primary = found[0]
        return primary, None, infer_device_label(primary), ""
    primary, compare = found[0], found[1]
    return primary, compare, infer_device_label(primary), infer_device_label(compare)


def default_window_json_path(log_path: Path | None = None) -> Path:
    base = log_path if log_path is not None else default_aplog_dir()
    return base / "analysis" / "game_time_window.json"


def resolve_window_json_path(log_path: Path, window_json: str | None) -> Path:
    if window_json and str(window_json).strip():
        return Path(window_json).resolve()
    return default_window_json_path(log_path)


def add_log_path_argument(parser: argparse.ArgumentParser, *, required: bool = False) -> None:
    if required:
        parser.add_argument("log_path", help=LOG_PATH_HELP)
    else:
        parser.add_argument("log_path", nargs="?", default=None, help=LOG_PATH_HELP)


def mobilelog_example_path() -> str:
    """文档用：相对 skillhub 的 mobilelog 示例路径。"""
    return (
        f"analysis/domain/power/flow/game/mobilelog/{DEFAULT_APLOG_NAME}"
    )
