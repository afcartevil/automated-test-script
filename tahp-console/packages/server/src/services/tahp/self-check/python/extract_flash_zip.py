#!/usr/bin/env python3
"""解压刷机 ZIP（zipfile 支持大于 2 GiB，替代 Node adm-zip）。"""
from __future__ import annotations

import os
import sys
import time
import zipfile
from pathlib import Path

CHUNK = 8 * 1024 * 1024
LARGE_FILE = 32 * 1024 * 1024


def format_size(num: int) -> str:
    gib = num / 1024 / 1024 / 1024
    if gib >= 1:
        return f"{gib:.2f} GiB"
    mib = num / 1024 / 1024
    if mib >= 1:
        return f"{mib:.1f} MiB"
    return f"{max(1, num // 1024)} KiB"


def member_target(dest: Path, filename: str) -> Path:
    normalized = filename.replace("\\", "/")
    if normalized.startswith("/") or (len(normalized) >= 2 and normalized[1] == ":"):
        raise ValueError(f"非法路径: {filename}")
    parts: list[str] = []
    for part in normalized.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            raise ValueError(f"非法路径: {filename}")
        parts.append(part)
    target = dest.joinpath(*parts)
    dest_resolved = str(dest.resolve())
    target_resolved = str(target.resolve())
    if os.path.commonpath([dest_resolved, target_resolved]) != dest_resolved:
        raise ValueError(f"非法路径: {filename}")
    return target


class Progress:
    def __init__(self, total: int) -> None:
        self.total = total
        self.done = 0
        self.current = ""
        self.last_pct = -1
        self.last_at = 0.0

    def advance(self, size: int, force: bool = False) -> None:
        self.done += size
        pct = 100 if self.total <= 0 else min(100, int(self.done * 100 / self.total))
        now = time.monotonic()
        if not force and pct == self.last_pct and now - self.last_at < 3:
            return
        if not force and pct < 100 and pct - self.last_pct < 5 and now - self.last_at < 3:
            return
        self.last_pct = pct
        self.last_at = now
        name = f" {self.current}" if self.current else ""
        print(
            f"解压进度 {pct}%（{format_size(self.done)}/{format_size(self.total)}）{name}",
            flush=True,
        )


def extract_member(zf: zipfile.ZipFile, info: zipfile.ZipInfo, dest: Path, progress: Progress) -> None:
    target = member_target(dest, info.filename)
    if info.is_dir() or info.filename.endswith("/"):
        target.mkdir(parents=True, exist_ok=True)
        return
    name = Path(info.filename).name
    progress.current = name
    if info.file_size >= LARGE_FILE:
        print(f"正在解压 {name}（{format_size(info.file_size)}）", flush=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    with zf.open(info, "r") as src, open(target, "wb") as out:
        while True:
            buf = src.read(CHUNK)
            if not buf:
                break
            out.write(buf)
            progress.advance(len(buf))
    if info.file_size == 0:
        progress.advance(0)


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
        infos = [info for info in zf.infolist() if not info.is_dir() and not info.filename.endswith("/")]
        total = sum(info.file_size for info in infos)
        print(f"共 {len(infos)} 个文件，约 {format_size(total)}", flush=True)
        progress = Progress(total)
        for info in zf.infolist():
            extract_member(zf, info, dest, progress)
        if progress.last_pct < 100:
            progress.advance(0, force=True)
    print(f"OK: {dest}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
