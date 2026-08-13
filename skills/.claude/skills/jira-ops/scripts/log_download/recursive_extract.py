"""Recursive archive extraction for Jira log downloads (modem log-pipeline port)."""

from __future__ import annotations

import bz2
import gzip
import os
import shutil
import subprocess
import tarfile
import zipfile
from collections import deque
from datetime import datetime
from typing import Any, Dict, List, Optional


def find_7z() -> Optional[str]:
    env_exe = os.environ.get("SEVEN_ZIP_EXE")
    if env_exe and os.path.exists(env_exe):
        return env_exe
    for name in ("7z", "7z.exe"):
        path = shutil.which(name)
        if path:
            return path
    for path in (
        r"C:\Program Files\7-Zip\7z.exe",
        r"C:\Program Files (x86)\7-Zip\7z.exe",
        r"C:\Program Files\NanaZip\7z.exe",
    ):
        if os.path.exists(path):
            return path
    return None


def _commonpath_safe(base_dir: str, target_path: str) -> str:
    try:
        return os.path.commonpath([base_dir, target_path])
    except ValueError:
        return ""


def _safe_member_path(destination: str, member_name: str) -> str:
    destination = os.path.abspath(destination)
    target_path = os.path.abspath(os.path.join(destination, member_name))
    if _commonpath_safe(destination, target_path) != destination:
        raise RuntimeError(f"检测到非法解压路径: {member_name}")
    return target_path


def _safe_extract_zip(zf: zipfile.ZipFile, destination: str) -> None:
    for member in zf.infolist():
        target_path = _safe_member_path(destination, member.filename)
        if member.is_dir():
            os.makedirs(target_path, exist_ok=True)
            continue
        if member.flag_bits & 0x1:
            raise RuntimeError(f"zip 成员被加密，无法直接解压: {member.filename}")
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        with zf.open(member, "r") as src, open(target_path, "wb") as dst:
            shutil.copyfileobj(src, dst)


def _safe_extract_tar(tf: tarfile.TarFile, destination: str) -> None:
    for member in tf.getmembers():
        target_path = _safe_member_path(destination, member.name)
        if member.isdir():
            os.makedirs(target_path, exist_ok=True)
            continue
        if not member.isfile():
            raise RuntimeError(f"tar 成员类型不支持: {member.name}")
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        extracted = tf.extractfile(member)
        if extracted is None:
            raise RuntimeError(f"无法读取 tar 成员: {member.name}")
        with extracted as src, open(target_path, "wb") as dst:
            shutil.copyfileobj(src, dst)


class StandaloneExtractor:
    def __init__(self) -> None:
        self.succeeded_files: List[str] = []
        self.failed_files: List[str] = []

    @staticmethod
    def is_compressed_file(path: str) -> bool:
        lower = path.lower()
        return lower.endswith((".zip", ".tar", ".gz", ".bz2", ".tgz", ".tbz2", ".rar", ".7z"))

    def extract(self, input_path: str, output_dir: Optional[str] = None, recursive: bool = True) -> bool:
        if os.path.isfile(input_path):
            return self.extract_single_file(input_path, output_dir)
        if not os.path.isdir(input_path):
            raise FileNotFoundError(f"路径不存在: {input_path}")

        file_list: deque[str] = deque()
        seen: set[str] = set()
        for root, _, files in os.walk(input_path):
            for name in files:
                path = os.path.join(root, name)
                if self.is_compressed_file(path):
                    file_list.append(path)

        any_success = False
        while file_list:
            file_path = file_list.popleft()
            if file_path in seen:
                continue
            seen.add(file_path)
            if self.extract_single_file(file_path, output_dir):
                any_success = True
            if recursive:
                for root, _, files in os.walk(input_path):
                    for name in files:
                        nested = os.path.join(root, name)
                        if nested not in seen and nested not in file_list and self.is_compressed_file(nested):
                            file_list.append(nested)
        return any_success

    def extract_single_file(self, file_path: str, output_dir: Optional[str] = None) -> bool:
        destination = output_dir or os.path.dirname(file_path) or "."
        os.makedirs(destination, exist_ok=True)
        lower = file_path.lower()
        try:
            if lower.endswith(".zip"):
                with zipfile.ZipFile(file_path, "r") as zf:
                    _safe_extract_zip(zf, destination)
            elif lower.endswith(".tar"):
                with tarfile.open(file_path, "r") as tf:
                    _safe_extract_tar(tf, destination)
            elif lower.endswith((".tgz", ".tar.gz")):
                with tarfile.open(file_path, "r:gz") as tf:
                    _safe_extract_tar(tf, destination)
            elif lower.endswith((".tbz2", ".tar.bz2")):
                with tarfile.open(file_path, "r:bz2") as tf:
                    _safe_extract_tar(tf, destination)
            elif lower.endswith(".gz") and not lower.endswith(".tar.gz"):
                output_file = os.path.join(destination, os.path.basename(file_path)[:-3])
                with gzip.open(file_path, "rb") as src, open(output_file, "wb") as dst:
                    shutil.copyfileobj(src, dst)
            elif lower.endswith(".bz2") and not lower.endswith(".tar.bz2"):
                output_file = os.path.join(destination, os.path.basename(file_path)[:-4])
                with bz2.open(file_path, "rb") as src, open(output_file, "wb") as dst:
                    shutil.copyfileobj(src, dst)
            elif lower.endswith((".rar", ".7z")):
                seven_zip = find_7z()
                if not seven_zip:
                    raise RuntimeError("未找到 7z，请安装 7-Zip 或设置 SEVEN_ZIP_EXE")
                cmd = [seven_zip, "x", "-y", f"-o{destination}", file_path]
                result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
                if result.returncode != 0:
                    combined = (result.stderr or "") + (result.stdout or "")
                    if "cannot set file attribute" not in combined.lower():
                        raise RuntimeError(combined.strip() or "7z 解压失败")
            else:
                raise RuntimeError(f"不支持的压缩格式: {file_path}")
            self.succeeded_files.append(file_path)
            return True
        except Exception:
            self.failed_files.append(file_path)
            return False


def _resolve_extracted_dir(abs_input: str, extractor: StandaloneExtractor) -> tuple[Optional[str], bool, bool]:
    if extractor.succeeded_files:
        return abs_input, True, False
    if extractor.succeeded_files or extractor.failed_files:
        return None, False, False
    if os.path.isdir(abs_input):
        return abs_input, True, True
    return None, False, False


def extract_directories(
    input_dirs: List[str],
    *,
    output_root: Optional[str] = None,
    recursive: bool = True,
) -> Dict[str, Any]:
    """Extract archives under each input directory; returns structured result."""
    if not input_dirs:
        raise ValueError("至少提供一个 --input-dir")

    extracted_dirs: List[str] = []
    results: List[Dict[str, Any]] = []

    for input_dir in input_dirs:
        abs_input = os.path.abspath(input_dir)
        extractor = StandaloneExtractor()
        item: Dict[str, Any] = {
            "input_dir": abs_input,
            "output_root": os.path.abspath(output_root) if output_root else "",
            "success": False,
            "succeeded_files": [],
            "failed_files": [],
        }
        try:
            item["success"] = bool(extractor.extract(abs_input, output_dir=output_root, recursive=recursive))
            item["succeeded_files"] = list(extractor.succeeded_files)
            item["failed_files"] = list(extractor.failed_files)
            resolved, ok, passthrough = _resolve_extracted_dir(abs_input, extractor)
            if resolved:
                if output_root:
                    resolved = os.path.abspath(output_root)
                extracted_dirs.append(resolved)
                item["success"] = ok
                if passthrough:
                    item["passthrough"] = True
                    item["note"] = "无压缩包，使用下载目录作为日志根"
            if extractor.failed_files and not extractor.succeeded_files:
                item["error"] = "所有压缩文件均解压失败"
            elif extractor.failed_files:
                item["error"] = "部分压缩文件解压失败"
        except Exception as exc:
            item["succeeded_files"] = list(extractor.succeeded_files)
            item["failed_files"] = list(extractor.failed_files)
            item["error"] = str(exc)
        results.append(item)

    extracted_dirs = list(dict.fromkeys(extracted_dirs))
    any_ok = any(r.get("success") for r in results)
    return {
        "extracted_dirs": extracted_dirs,
        "results": results,
        "extracted_any": any_ok,
        "seven_zip": find_7z(),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }
