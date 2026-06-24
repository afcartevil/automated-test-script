#!/usr/bin/env python3
"""从 monorepo 上游刷新本 skill 包（analysis_skills、scripts、log-pipeline 等）。

仅在 skills 仓库内有效；独立交付副本若无上游目录会报错。

用法（skill 根目录）：
    python scripts/sync_from_upstream.py
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = SKILL_ROOT.parent.parent.parent  # modem-analysis-local -> skills -> repo
UNIFIED = REPO_ROOT / ".agents" / "skills" / "modem-analysis-unified"
PIPELINE = REPO_ROOT / "modem-log-pipeline"

SKIP_DIR_NAMES = {
    "__pycache__",
    ".venv",
    "data_store_linux",
    "examples",
    ".git",
}
SKIP_FILE_NAMES = {
    ".env",
    "sync_issue_from_share.py",
    "syslog.txt",
    "SKILL.md",
    "README.md",
}
SKIP_SUFFIXES = (".pyc",)


def should_skip(path: Path) -> bool:
    if path.name in SKIP_FILE_NAMES:
        return True
    if path.suffix in SKIP_SUFFIXES:
        return True
    return False


def copy_tree(src: Path, dst: Path, *, skip_top_level: set[str] | None = None) -> int:
    if not src.is_dir():
        raise SystemExit(f"missing source: {src}")
    n = 0
    skip_top_level = skip_top_level or set()
    for item in src.rglob("*"):
        rel = item.relative_to(src)
        if rel.parts and rel.parts[0] in skip_top_level:
            continue
        if any(p in SKIP_DIR_NAMES for p in rel.parts):
            continue
        if item.is_dir():
            continue
        if should_skip(item):
            continue
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)
        n += 1
    return n


def main() -> int:
    if not UNIFIED.is_dir():
        print(f"UNIFIED not found: {UNIFIED}", file=sys.stderr)
        return 1
    if not PIPELINE.is_dir():
        print(f"PIPELINE not found: {PIPELINE}", file=sys.stderr)
        return 1

    unified_items = [
        "analysis_skills",
        "schemas",
        "references",
    ]
    total = 0
    for name in unified_items:
        src = UNIFIED / name
        if not src.is_dir():
            print(f"skip missing: {src}")
            continue
        dst = SKILL_ROOT / name
        if dst.exists():
            shutil.rmtree(dst)
        c = copy_tree(src, dst)
        print(f"copied {c} files: {name}/")
        total += c

    sync_self = Path(__file__).resolve()
    sync_backup = sync_self.read_bytes()
    scripts_src = UNIFIED / "scripts"
    scripts_dst = SKILL_ROOT / "scripts"
    if scripts_dst.exists():
        shutil.rmtree(scripts_dst)
    c = copy_tree(scripts_src, scripts_dst)
    sync_self.write_bytes(sync_backup)
    print(f"copied {c} files: scripts/ (preserved sync_from_upstream.py)")
    total += c

    lp_dst = SKILL_ROOT / "log-pipeline"
    if lp_dst.exists():
        shutil.rmtree(lp_dst)
    c = copy_tree(PIPELINE, lp_dst, skip_top_level={"scripts", "docs"})
    print(f"copied {c} files: log-pipeline/")
    total += c

    print(f"total files: {total}")
    print("note: SKILL.md / README.md / .env.example 未覆盖，请手工合并")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
