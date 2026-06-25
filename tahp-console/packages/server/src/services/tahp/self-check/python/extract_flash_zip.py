#!/usr/bin/env python3
"""解压刷机 ZIP（zipfile 支持大于 2 GiB，替代 Node adm-zip）。"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: extract_flash_zip.py <zip> <dest_dir>", file=sys.stderr)
        return 2
    zip_path = Path(sys.argv[1])
    dest = Path(sys.argv[2])
    if not zip_path.is_file():
        print(f"ZIP 不存在: {zip_path}", file=sys.stderr)
        return 1
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(dest)
    print(f"OK: {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
