#!/usr/bin/env python3
"""DOU 日志 zip 解压（与 mobile_log 相同规则：zip → 同目录下去后缀文件夹，已存在则跳过）。

工作区根解析见 analysis/base/lib/repo_paths.py。
"""

from __future__ import annotations

import os
import zipfile
from pathlib import Path
from typing import List, Optional, Union

RootPath = Union[str, Path]

# bugreport zip 内含大量 FS/ 深路径，UNC 上易触发 Windows MAX_PATH；
# AudioMix / Longwake 只需要根目录主 txt。为避开「目录名+文件名」叠加超长，
# 主 txt 固定落到 bugreports/bugreport_main.txt（短路径）。
_BUGREPORT_MAIN_NAME = "bugreport_main.txt"
_ARTIFACT_TXT_NAMES = {
    "bugreport_audiomix.txt",
    "bugreport_longwake.txt",
    "bugreport_audiomix_result.txt",
}


def _is_bugreport_zip(zp: Path) -> bool:
    name = zp.name.lower()
    return name.startswith("bugreport") and name.endswith(".zip")


def _win_long_path(path: Path | str) -> str:
    """Windows 长路径前缀，避免 UNC MAX_PATH 失败。"""
    s = os.path.abspath(str(path))
    if os.name != "nt":
        return s
    if s.startswith("\\\\?\\"):
        return s
    if s.startswith("\\\\"):
        return "\\\\?\\UNC\\" + s.lstrip("\\")
    return "\\\\?\\" + s


def _pick_bugreport_member(zf: zipfile.ZipFile) -> Optional[zipfile.ZipInfo]:
    """选 zip 根目录下体积最大的真实 bugreport*.txt（排除 dumpstate）。"""
    best: Optional[zipfile.ZipInfo] = None
    best_size = -1
    for info in zf.infolist():
        norm = info.filename.replace("\\", "/").lstrip("./")
        if not norm or norm.endswith("/") or "/" in norm:
            continue
        lower = Path(norm).name.lower()
        if not lower.startswith("bugreport") or not lower.endswith(".txt"):
            continue
        if "dumpstate" in lower:
            continue
        if info.file_size > best_size:
            best = info
            best_size = info.file_size
    return best


def _bugreport_main_ready(bugreports_dir: Path) -> bool:
    main = bugreports_dir / _BUGREPORT_MAIN_NAME
    try:
        return main.is_file() and main.stat().st_size > 1024
    except OSError:
        return False


def _extract_bugreport_main(zp: Path) -> Optional[str]:
    """把 bugreport zip 中的主 txt 解到同级 ``bugreport_main.txt``（短文件名）。"""
    bugreports_dir = zp.parent
    out_file = bugreports_dir / _BUGREPORT_MAIN_NAME
    if _bugreport_main_ready(bugreports_dir):
        return str(bugreports_dir)
    try:
        with zipfile.ZipFile(zp, "r") as zf:
            info = _pick_bugreport_member(zf)
            if info is None:
                return None
            target_lp = _win_long_path(out_file)
            parent = os.path.dirname(target_lp)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with zf.open(info) as src, open(target_lp, "wb") as dst:
                while True:
                    chunk = src.read(1024 * 1024)
                    if not chunk:
                        break
                    dst.write(chunk)
    except (zipfile.BadZipFile, OSError):
        return None
    if _bugreport_main_ready(bugreports_dir):
        return str(bugreports_dir)
    return None


def _extract_member_longpath(zf: zipfile.ZipFile, info: zipfile.ZipInfo, out_dir: Path) -> None:
    """写出 zip 成员到 out_dir，目标路径走长路径 API。"""
    name = info.filename.replace("\\", "/").lstrip("./")
    if not name or name.endswith("/"):
        return
    target = out_dir / Path(name).name
    target_lp = _win_long_path(target)
    parent = os.path.dirname(target_lp)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with zf.open(info) as src, open(target_lp, "wb") as dst:
        while True:
            chunk = src.read(1024 * 1024)
            if not chunk:
                break
            dst.write(chunk)


def expand_zip_if_needed(zip_path: RootPath) -> Optional[str]:
    """解压单个 zip 到 ``<parent>/<stem>/``；目标目录已存在则跳过。

    bugreport*.zip：主 txt 落到 ``bugreports/bugreport_main.txt``（短路径）。
    """
    zp = Path(zip_path).resolve()
    if not zp.is_file() or zp.suffix.lower() != ".zip":
        return None

    if _is_bugreport_zip(zp):
        return _extract_bugreport_main(zp)

    out_dir = zp.parent / zp.stem
    if out_dir.is_dir():
        return str(out_dir)
    os.makedirs(_win_long_path(out_dir), exist_ok=True)

    try:
        with zipfile.ZipFile(zp, "r") as zf:
            try:
                zf.extractall(out_dir)
            except OSError:
                for info in zf.infolist():
                    _extract_member_longpath(zf, info, out_dir)
    except zipfile.BadZipFile:
        return None
    return str(out_dir)


def ensure_mobile_log_extracted(root: RootPath) -> List[str]:
    """解压 ``phone_logs/mobile_log*.zip``（取第一个，与 run_dou_jira_prepare.ps1 一致）。"""
    root = Path(root).resolve()
    phone_logs = root / "phone_logs"
    if not phone_logs.is_dir():
        return []
    zips = sorted(phone_logs.glob("mobile_log*.zip"))
    if not zips:
        return []
    out = expand_zip_if_needed(zips[0])
    return [out] if out else []


def ensure_bugreport_extracted(root: RootPath) -> List[str]:
    """先解压 mobile_log，再解压 ``phone_logs/**/bugreports/bugreport*.zip``。"""
    root = Path(root).resolve()
    ensure_mobile_log_extracted(root)
    extracted: List[str] = []
    for zp in sorted(root.glob("phone_logs/**/bugreports/bugreport*.zip")):
        out = expand_zip_if_needed(zp)
        if out:
            extracted.append(out)
    return extracted


def ensure_dou_phone_logs_extracted(root: RootPath) -> dict[str, List[str]]:
    """高/低功耗目录一次性解压 mobile_log + bugreport。"""
    mobile = ensure_mobile_log_extracted(root)
    bugreport = ensure_bugreport_extracted(root)
    return {"mobile_log": mobile, "bugreport": bugreport}
