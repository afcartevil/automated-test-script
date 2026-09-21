"""TNE file parser — extract and decompress all files from .tne archives.

TNE files are tar archives produced by device crash dump (tran_pdb).
Each .tne contains a directory structure like:
    data/TNE/<name>/<file1>.zs
    data/TNE/<name>/<file2>.zs
    ...

Files with .zs extension are zstd-decompressed when extracted from the TNE tar.
Directory structure inside the tar (e.g. data/TNE/...) is preserved.
After extraction, .zlib files and nested tar/.zs archives are expanded automatically.

Usage (standalone):
    python tne_parser.py <tne_file_or_dir> [--output <dir>]
"""

from __future__ import annotations

import argparse
import io
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Outer archive suffixes handled during nested expansion (longest first).
_NESTED_ARCHIVE_SUFFIXES = (
    ".tar.gz",
    ".tar.zs",
    ".tar.zlib",
    ".tgz",
    ".tar",
    ".zs",
    ".zlib",
)

# TNE filename pattern: 0xffffff04_2025_06_13_16_48_12.tne
TNE_NAME_RE = re.compile(
    r"^(?:0x[0-9a-f]+_)?(\d{4})_(\d{2})_(\d{2})_(\d{2})_(\d{2})_(\d{2})\.tne$",
    re.IGNORECASE,
)

# Plain TNE tar archives start with this path prefix inside the first tar header.
_TNE_TAR_MAGIC = b"data/TNE/"

# Fixed AES-128-ECB key from TneDecompress (AesCryptDescrypt2.cpp / decrypt_file).
_TNE_AES_KEY = b"*#2020usic_rd*#z"


@dataclass
class TneFileInfo:
    """Info about a single file inside a TNE archive."""
    archive_name: str  # original name in tar (e.g. data/TNE/xxx/file.zs)
    extracted_name: str  # filename after removing outer .zs
    relative_path: str  # path under extraction root, e.g. data/TNE/xxx/file.zlib
    size: int  # decompressed size in bytes
    data: bytes  # decompressed content


@dataclass
class TneParseResult:
    """Result of parsing a TNE file."""
    tne_path: str
    tne_name: str  # e.g. "0xffffff04_2025_06_13_16_48_12"
    timestamp: Optional[datetime]
    files: Dict[str, TneFileInfo] = field(default_factory=dict)  # key = relative_path (lower)
    _directories: List[str] = field(default_factory=list)  # directories in tar

    def get_file(self, name: str) -> Optional[TneFileInfo]:
        """Get a file by name (case-insensitive, without .zs/.zlib suffix)."""
        key = name.lower().replace(".zs", "").replace(".zlib", "")
        direct = self.files.get(key)
        if direct is not None:
            return direct
        for info in self.files.values():
            extracted = info.extracted_name.lower()
            if extracted == key or extracted.replace(".zlib", "") == key:
                return info
            if Path(info.relative_path).name.lower().replace(".zlib", "") == key:
                return info
        return None

    def _store_file(self, info: TneFileInfo) -> None:
        """Store file info keyed by relative path."""
        self.files[info.relative_path.replace("\\", "/").lower()] = info

    def get_file_data(self, name: str) -> Optional[bytes]:
        """Get raw bytes of a file by name."""
        info = self.get_file(name)
        return info.data if info else None

    def find_file_containing(self, substring: str) -> Optional[TneFileInfo]:
        """Find first file whose extracted_name contains substring (case-insensitive)."""
        sub = substring.lower()
        for info in self.files.values():
            if sub in info.extracted_name.lower():
                return info
        return None

    def find_file_data_containing(self, substring: str) -> Optional[bytes]:
        """Get raw bytes of first file whose name contains substring."""
        info = self.find_file_containing(substring)
        return info.data if info else None

    def list_files(self) -> List[str]:
        """List all extracted relative paths."""
        return sorted(info.relative_path for info in self.files.values())

    def detect_platform(self) -> str:
        """Detect platform type based on directory structure and file presence.

        Detection order:
          1. Qualcomm: has tmp.tar or md_TRAN_EXP_INF.BIN
             (tmp.tar contains md_TRAN_EXP_INF.BIN after extraction)
          2. Spreadtrum: has kernel/, modem/, bootloader/ directories
          3. MTK: fallback (flat file structure)

        Returns:
            "qualcomm", "spreadtrum", or "mtk"
        """
        # Qualcomm: tmp.tar (inside tne) or md_TRAN_EXP_INF.BIN (already extracted)
        if any(
            info.extracted_name.lower() in ("tmp.tar", "md_tran_exp_inf.bin")
            for info in self.files.values()
        ):
            return "qualcomm"

        spreadtrum_dirs = {"kernel", "modem", "bootloader"}
        found_dirs = set()

        for dir_path in self._directories:
            # Extract the last directory name from path like "data/TNE/xxx/kernel"
            # Handle both '/' (tar archive) and '\' (Windows path from parse_extracted_dir)
            normalized = dir_path.replace("\\", "/")
            parts = normalized.rstrip("/").split("/")
            if parts:
                found_dirs.add(parts[-1].lower())

        if spreadtrum_dirs & found_dirs:
            return "spreadtrum"
        return "mtk"


def _decompress_zs(data: bytes) -> bytes:
    """Decompress zstd (.zs) data."""
    if not data:
        return b""
    import zstandard as zstd
    dctx = zstd.ZstdDecompressor()
    return dctx.decompress(data, max_output_size=200 * 1024 * 1024)


def _decompress_zlib(data: bytes) -> bytes:
    """Decompress zlib (.zlib) data."""
    if not data:
        return b""
    import zlib
    return zlib.decompress(data)


def _decompress_chain(name: str, data: bytes) -> Tuple[str, bytes]:
    """Decompress chained suffixes (e.g. foo.zlib.zs -> foo)."""
    extracted_name = name
    while True:
        name_lower = extracted_name.lower()
        if name_lower.endswith(".zs"):
            data = _decompress_zs(data)
            extracted_name = extracted_name[:-3]
        elif name_lower.endswith(".zlib"):
            data = _decompress_zlib(data)
            extracted_name = extracted_name[:-5]
        else:
            break
    return extracted_name, data


def _decompress_tne_member(name: str, data: bytes) -> Tuple[str, bytes]:
    """Decompress only the outer .zs wrapper from a TNE tar member."""
    if name.lower().endswith(".zs"):
        if data:
            data = _decompress_zs(data)
        name = name[:-3]
    return name, data


def _archive_relative_path(archive_name: str, extracted_name: str) -> str:
    """Build output relative path, preserving tar directory structure."""
    parent = Path(archive_name.replace("\\", "/")).parent
    if str(parent) in ("", "."):
        return extracted_name
    return str(parent / extracted_name).replace("\\", "/")


def _nested_archive_output_dir(archive_path: Path) -> Path:
    """Return output directory for a nested archive file."""
    name = archive_path.name
    for suffix in _NESTED_ARCHIVE_SUFFIXES:
        if name.lower().endswith(suffix):
            return archive_path.parent / name[: -len(suffix)]
    return archive_path.parent / archive_path.stem


def _is_tar_archive(path: Path) -> bool:
    name = path.name.lower()
    return name.endswith((".tar", ".tgz", ".tar.gz"))


def _extract_tar_to_dir(tar_path: Path, output_dir: Path) -> int:
    """Extract a tar archive to output_dir, preserving member paths."""
    output_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    with tarfile.open(str(tar_path), "r:*") as tf:
        for member in tf.getmembers():
            if not member.isfile():
                continue
            f = tf.extractfile(member)
            if not f:
                continue
            raw_data = f.read()
            basename = os.path.basename(member.name)
            extracted_name, data = _decompress_chain(basename, raw_data)
            relative_path = _archive_relative_path(member.name, extracted_name)
            out_path = output_dir / relative_path
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(data)
            count += 1
    return count


def _expand_nested_archive_file(path: Path) -> bool:
    """Expand one nested archive/compressed file. Returns True if handled."""
    name_lower = path.name.lower()

    if _is_tar_archive(path):
        out_dir = _nested_archive_output_dir(path)
        if out_dir.exists() and any(out_dir.iterdir()):
            return False
        count = _extract_tar_to_dir(path, out_dir)
        print(f"[TNE] 已解压嵌套 tar: {path.name} -> {out_dir.name}/ ({count} 个文件)")
        return True

    if name_lower.endswith(".zs") or name_lower.endswith(".zlib"):
        extracted_name, data = _decompress_chain(path.name, path.read_bytes())
        if extracted_name.lower() == name_lower:
            return False
        out_path = path.parent / extracted_name
        if out_path.exists():
            return False
        out_path.write_bytes(data)
        try:
            path.unlink()
        except OSError:
            pass
        print(f"[TNE] 已解压嵌套压缩包: {path.name} -> {extracted_name}")
        return True

    return False


def expand_nested_archives(root_dir: Path, max_passes: int = 20) -> int:
    """Recursively expand nested tar/.zs/.zlib files under root_dir."""
    total = 0
    for _ in range(max_passes):
        expanded_this_pass = 0
        files = sorted(
            (p for p in root_dir.rglob("*") if p.is_file()),
            key=lambda p: len(p.parts),
            reverse=True,
        )
        for path in files:
            if _expand_nested_archive_file(path):
                expanded_this_pass += 1
        total += expanded_this_pass
        if expanded_this_pass == 0:
            break
    return total


def parse_tne_time(filename: str) -> Optional[datetime]:
    """Parse timestamp from TNE filename like 0xffffff04_2025_06_13_16_48_12.tne."""
    m = TNE_NAME_RE.match(filename)
    if not m:
        return None
    try:
        return datetime(
            int(m.group(1)), int(m.group(2)), int(m.group(3)),
            int(m.group(4)), int(m.group(5)), int(m.group(6)),
        )
    except ValueError:
        return None


def find_latest_tne(directory: str) -> Optional[str]:
    """Find the most recent .tne file in a directory (by filename timestamp)."""
    files = find_recent_tne_files(directory, max_age_days=90)
    return files[0] if files else None


def find_recent_tne_files(directory: str, max_age_days: int = 90) -> List[str]:
    """Find .tne files in a directory, sorted by timestamp (newest first).

    Filters out files older than max_age_days.

    Args:
        directory: Directory to search for .tne files.
        max_age_days: Maximum age in days (default 90 = ~3 months).

    Returns:
        List of tne file paths sorted by timestamp (newest first).
    """
    dir_path = Path(directory)
    if not dir_path.is_dir():
        return []

    now = datetime.now()
    cutoff = now.replace(hour=0, minute=0, second=0, microsecond=0)
    from datetime import timedelta
    cutoff = cutoff - timedelta(days=max_age_days)

    tne_files = []
    for f in dir_path.iterdir():
        if f.suffix.lower() == ".tne" and f.is_file():
            t = parse_tne_time(f.name)
            if t and t >= cutoff:
                tne_files.append((t, str(f)))

    tne_files.sort(key=lambda x: x[0], reverse=True)
    return [path for _, path in tne_files]


def find_tne_files(directory: str) -> List[str]:
    """Find all .tne files in a directory (non-recursive).

    Sorted by filename timestamp when available (newest first), otherwise
    by filename.
    """
    dir_path = Path(directory)
    if not dir_path.is_dir():
        return []

    tne_files: List[Tuple[datetime, str, str]] = []
    for f in dir_path.iterdir():
        if f.suffix.lower() == ".tne" and f.is_file():
            t = parse_tne_time(f.name)
            sort_key = t if t is not None else datetime.min
            tne_files.append((sort_key, f.name.lower(), str(f)))

    tne_files.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [path for _, _, path in tne_files]


def is_encrypted_tne(tne_path: str) -> bool:
    """Return True if the .tne file is AES-encrypted (not a plain tar archive).

    Encrypted TNE files have high-entropy contents and do not begin with the
    ``data/TNE/`` tar header prefix used by unencrypted archives.
    """
    path = Path(tne_path)
    if not path.is_file():
        raise FileNotFoundError(f"TNE file not found: {tne_path}")

    head = path.read_bytes()[:512]
    if head.startswith(_TNE_TAR_MAGIC):
        return False

    try:
        with tarfile.open(str(path), "r:*") as tf:
            tf.getmembers()
        return False
    except tarfile.TarError:
        return True


def decrypt_tne_bytes(data: bytes) -> bytes:
    """Decrypt AES-128-ECB encrypted TNE data (same key as TneDecompress).

    Args:
        data: Raw encrypted .tne bytes (length must be a multiple of 16).

    Returns:
        Decrypted tar archive bytes.

    Raises:
        ValueError: If data length is not block-aligned.
        ImportError: If pycryptodome is not installed.
    """
    if len(data) % 16:
        raise ValueError(f"encrypted TNE size must be multiple of 16, got {len(data)}")

    try:
        from Crypto.Cipher import AES
    except ImportError as exc:
        raise ImportError(
            "解密加密 TNE 需要 pycryptodome：pip install pycryptodome"
        ) from exc

    cipher = AES.new(_TNE_AES_KEY, AES.MODE_ECB)
    return cipher.decrypt(data)


def read_tne_bytes(tne_path: str, *, auto_decrypt: bool = True) -> bytes:
    """Read a .tne file, decrypting first when needed."""
    data = Path(tne_path).read_bytes()
    if auto_decrypt and not data.startswith(_TNE_TAR_MAGIC):
        try:
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as tf:
                tf.getmembers()
            return data
        except tarfile.TarError:
            data = decrypt_tne_bytes(data)
            print(f"[TNE] 已解密加密文件: {Path(tne_path).name}")
    return data


def find_tne_decompress_exe(explicit: Optional[str] = None) -> Optional[Path]:
    """Locate TneDecompress used as fallback when pycryptodome is unavailable."""
    candidates: List[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    env_path = os.environ.get("TNE_DECOMPRESS_EXE")
    if env_path:
        candidates.append(Path(env_path))

    which = shutil.which("TneDecompress.exe") or shutil.which("tne_decompress")
    if which:
        candidates.append(Path(which))

    script_dir = Path(__file__).resolve().parent
    candidates.extend(
        (
            script_dir / "TneDecompress.exe",
            script_dir / "TneDecompress" / "TneDecompress.exe",
            script_dir / "tne_decompress",
        )
    )

    seen = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        if candidate.is_file():
            return candidate
    return None


def decrypt_tne_file(
    tne_path: str,
    tool_exe: Optional[str] = None,
) -> Path:
    """Decrypt an encrypted .tne file to a temporary plain tar copy.

    Uses built-in AES decrypt by default; falls back to TneDecompress when
    pycryptodome is not installed.
    """
    src = Path(tne_path)
    if not src.is_file():
        raise FileNotFoundError(f"TNE file not found: {tne_path}")

    tmp_root = Path(tempfile.mkdtemp(prefix="tne_decrypt_"))
    local_tne = tmp_root / src.name

    try:
        plain = read_tne_bytes(str(src))
        local_tne.write_bytes(plain)
        return local_tne
    except ImportError:
        pass

    exe = find_tne_decompress_exe(tool_exe)
    if exe is None:
        raise FileNotFoundError(
            "无法解密加密 TNE：请安装 pycryptodome（pip install pycryptodome），"
            "或设置 TNE_DECOMPRESS_EXE 指向 TneDecompress 工具。"
        )

    work_dir = tmp_root / "work"
    work_dir.mkdir()
    local_tne = work_dir / src.name
    shutil.copy2(src, local_tne)

    if exe.name.lower() in ("tne_decompress", "tne_decompress.exe"):
        # Linux: parent dir must be named "tne", run `./tne_decompress tne`
        tne_dir = tmp_root / "tne"
        tne_dir.mkdir()
        shutil.copy2(src, tne_dir / src.name)
        cmd = [str(exe), "tne"]
        cwd = str(tmp_root)
    else:
        cmd = [str(exe), "/k", "cd", str(work_dir)]
        cwd = None

    completed = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=cwd,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "TneDecompress 解密失败: "
            f"exit={completed.returncode}, stderr={completed.stderr.strip()}"
        )

    out_tne = tne_dir / src.name if exe.name.lower().startswith("tne_decompress") else local_tne
    if is_encrypted_tne(str(out_tne)):
        detail = (completed.stdout or completed.stderr or "").strip()
        raise RuntimeError(
            "TNE 解密后仍无法识别为 tar 归档。"
            + (f" 工具输出: {detail}" if detail else "")
        )

    print(f"[TNE] 已解密加密文件: {src.name}")
    return out_tne


def parse_tne(
    tne_path: str,
    *,
    auto_decrypt: bool = True,
    tne_decompress_exe: Optional[str] = None,
) -> TneParseResult:
    """Parse a .tne file, extracting and decompressing all files.

    Args:
        tne_path: Path to the .tne file (tar archive).
        auto_decrypt: When True, decrypt AES-encrypted .tne files before parsing.
        tne_decompress_exe: Optional fallback path to TneDecompress binary.

    Returns:
        TneParseResult with all files decompressed and accessible by name.

    Raises:
        FileNotFoundError: If tne_path does not exist.
        tarfile.TarError: If the file is not a valid tar archive.
    """
    path = Path(tne_path)
    if not path.is_file():
        raise FileNotFoundError(f"TNE file not found: {tne_path}")

    try:
        tar_data = read_tne_bytes(str(path), auto_decrypt=auto_decrypt)
    except ImportError:
        if not auto_decrypt or not is_encrypted_tne(str(path)):
            tar_data = path.read_bytes()
        else:
            parse_path = decrypt_tne_file(str(path), tool_exe=tne_decompress_exe)
            tar_data = parse_path.read_bytes()

    tne_name = path.stem  # e.g. "0xffffff04_2025_06_13_16_48_12"
    timestamp = parse_tne_time(path.name)

    result = TneParseResult(
        tne_path=str(path),
        tne_name=tne_name,
        timestamp=timestamp,
    )

    with tarfile.open(fileobj=io.BytesIO(tar_data), mode="r:*") as tf:
        for member in tf.getmembers():
            # Collect directories for platform detection
            if member.isdir():
                result._directories.append(member.name)
                continue

            if not member.isfile():
                continue

            f = tf.extractfile(member)
            if not f:
                continue

            raw_data = f.read()
            archive_name = member.name
            basename = os.path.basename(archive_name)

            # Only strip the outer .zs wrapper, same as the official TNE tool.
            extracted_name, data = _decompress_tne_member(basename, raw_data)
            relative_path = _archive_relative_path(archive_name, extracted_name)

            info = TneFileInfo(
                archive_name=archive_name,
                extracted_name=extracted_name,
                relative_path=relative_path,
                size=len(data),
                data=data,
            )
            result._store_file(info)

    return result


def parse_extracted_dir(dir_path: str) -> TneParseResult:
    """Build a TneParseResult from an already-extracted directory.

    Reads all files under dir_path into TneParseResult.files (keyed by
    lowercase filename).  Subdirectory names are recorded for platform
    detection via detect_platform().

    Args:
        dir_path: Path to the extracted directory.

    Returns:
        TneParseResult populated from directory contents.

    Raises:
        NotADirectoryError: If dir_path is not a directory.
    """
    root = Path(dir_path)
    if not root.is_dir():
        raise NotADirectoryError(f"不是有效目录: {dir_path}")

    result = TneParseResult(
        tne_path=str(root),
        tne_name=root.name,
        timestamp=None,
    )

    # 第一遍：收集所有文件路径，区分已解压和未解压
    all_files: List[Path] = []
    for path in root.rglob("*"):
        if path.is_dir():
            result._directories.append(str(path.relative_to(root)))
        elif path.is_file():
            all_files.append(path)

    # 判断文件名是否为压缩格式
    def _is_compressed(name: str) -> bool:
        low = name.lower()
        return low.endswith(".zs") or low.endswith(".zlib")

    # 计算解压后的目标文件名
    def _final_name(name: str) -> str:
        n = name
        while True:
            low = n.lower()
            if low.endswith(".zs"):
                n = n[:-3]
            elif low.endswith(".zlib"):
                n = n[:-5]
            else:
                return n

    # 第二遍：优先处理已解压文件，压缩文件仅在无已解压版本时使用
    compressed_pending: List[Path] = []
    for path in all_files:
        if _is_compressed(path.name):
            compressed_pending.append(path)
        else:
            rel_path = str(path.relative_to(root)).replace("\\", "/")
            data = path.read_bytes()
            result._store_file(TneFileInfo(
                archive_name=rel_path,
                extracted_name=path.name,
                relative_path=rel_path,
                size=len(data),
                data=data,
            ))

    # 第三遍：处理压缩文件，若已解压版本已存在则跳过
    for path in compressed_pending:
        rel_path = str(path.relative_to(root)).replace("\\", "/")
        extracted_name, data = _decompress_tne_member(path.name, path.read_bytes())
        if extracted_name != path.name:
            rel_path = str(Path(rel_path).with_name(extracted_name)).replace("\\", "/")
        if rel_path.replace("\\", "/").lower() in result.files:
            continue  # 已解压版本已存在，跳过
        result._store_file(TneFileInfo(
            archive_name=rel_path,
            extracted_name=extracted_name,
            relative_path=rel_path,
            size=len(data),
            data=data,
        ))

    return result


def extract_tne_to_dir(
    tne_path: str,
    output_dir: str,
    expand_nested: bool = True,
    auto_decrypt: bool = True,
    tne_decompress_exe: Optional[str] = None,
) -> Path:
    """Parse a .tne file and write all extracted files to output_dir.

    Args:
        tne_path: Path to the .tne file.
        output_dir: Directory to write extracted files into.
        expand_nested: Also extract nested tar/.zs/.zlib files in output.
        auto_decrypt: Decrypt AES-encrypted .tne files before parsing.
        tne_decompress_exe: Optional path to TneDecompress.exe.

    Returns:
        Path to the output directory.
    """
    result = parse_tne(
        tne_path,
        auto_decrypt=auto_decrypt,
        tne_decompress_exe=tne_decompress_exe,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    for info in result.files.values():
        out_path = out / info.relative_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(info.data)

    print(f"[TNE] 已解压 {len(result.files)} 个文件到 {out}")

    if expand_nested:
        nested_count = expand_nested_archives(out)
        if nested_count:
            print(f"[TNE] 共处理 {nested_count} 个嵌套压缩包")

    return out


def extract_tne_directory(
    directory: str,
    output_dir: Optional[str] = None,
    expand_nested: bool = True,
    auto_decrypt: bool = True,
    tne_decompress_exe: Optional[str] = None,
) -> List[Path]:
    """Extract all .tne files in a directory (non-recursive).

    Each archive is written to ``<output>/<stem>_extracted/`` when *output_dir*
    is given, otherwise ``<tne_dir>/<stem>_extracted/``.

    Returns:
        List of output directories, one per .tne file.

    Raises:
        NotADirectoryError: If *directory* is not a directory.
        FileNotFoundError: If no .tne files are found.
    """
    dir_path = Path(directory)
    if not dir_path.is_dir():
        raise NotADirectoryError(f"不是有效目录: {directory}")

    tne_files = find_tne_files(directory)
    if not tne_files:
        raise FileNotFoundError(f"目录下未找到 .tne 文件: {directory}")

    outputs: List[Path] = []
    for tne_path in tne_files:
        stem = Path(tne_path).stem
        if output_dir:
            out = Path(output_dir) / f"{stem}_extracted"
        else:
            out = dir_path / f"{stem}_extracted"
        extract_tne_to_dir(
            tne_path,
            str(out),
            expand_nested=expand_nested,
            auto_decrypt=auto_decrypt,
            tne_decompress_exe=tne_decompress_exe,
        )
        outputs.append(out)

    print(f"[TNE] 目录 {dir_path} 共解压 {len(outputs)} 个 TNE 文件")
    return outputs


def main():
    """CLI entry point: python tne_parser.py <tne_file_or_dir> [--output <dir>]"""
    parser = argparse.ArgumentParser(
        description="解析 TNE 日志文件（tar 归档），解压所有文件；支持单个文件或目录"
    )
    parser.add_argument(
        "tne_file",
        nargs="?",
        help="TNE 文件路径，或包含 .tne 文件的目录",
    )
    parser.add_argument(
        "--output", "-o",
        help="输出目录（单文件: <name>_extracted/；目录: 每个 TNE 写入 <output>/<name>_extracted/）",
    )
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="仅列出文件，不解压",
    )
    parser.add_argument(
        "--no-nested",
        action="store_true",
        help="不递归解压嵌套 .zlib / tar / .zs 文件",
    )
    parser.add_argument(
        "--no-decrypt",
        action="store_true",
        help="不尝试解密 AES 加密的 .tne（默认会自动解密）",
    )
    parser.add_argument(
        "--tne-decompress-exe",
        help="TneDecompress.exe 路径（也可用环境变量 TNE_DECOMPRESS_EXE）",
    )
    parser.add_argument(
        "--expand-nested-only",
        metavar="DIR",
        help="仅对已有解压目录递归处理嵌套压缩包",
    )
    args = parser.parse_args()

    if args.expand_nested_only:
        nested_count = expand_nested_archives(Path(args.expand_nested_only))
        print(f"[TNE] 共处理 {nested_count} 个嵌套压缩包")
        return

    if not args.tne_file:
        parser.error("需要提供 tne_file 或目录，或使用 --expand-nested-only DIR")

    input_path = Path(args.tne_file)
    if not input_path.exists():
        parser.error(f"路径不存在: {args.tne_file}")

    decrypt_kwargs = {
        "auto_decrypt": not args.no_decrypt,
        "tne_decompress_exe": args.tne_decompress_exe,
    }

    if input_path.is_dir():
        if args.list:
            tne_files = find_tne_files(str(input_path))
            if not tne_files:
                print(f"目录下未找到 .tne 文件: {input_path}")
                return
            for tne_path in tne_files:
                result = parse_tne(tne_path, **decrypt_kwargs)
                print(f"TNE: {result.tne_name}")
                print(f"时间: {result.timestamp}")
                print(f"文件数: {len(result.files)}")
                for info in sorted(result.files.values(), key=lambda x: x.relative_path):
                    print(f"  {info.relative_path:60s}  {info.size:>10,} bytes")
                print()
            print(f"共 {len(tne_files)} 个 TNE 文件")
            return

        extract_tne_directory(
            str(input_path),
            output_dir=args.output,
            expand_nested=not args.no_nested,
            **decrypt_kwargs,
        )
        return

    if not input_path.is_file():
        parser.error(f"不是有效的 TNE 文件: {args.tne_file}")

    tne_path = str(input_path)

    if args.list:
        result = parse_tne(tne_path, **decrypt_kwargs)
        print(f"TNE: {result.tne_name}")
        print(f"时间: {result.timestamp}")
        print(f"文件数: {len(result.files)}")
        print()
        for info in sorted(result.files.values(), key=lambda x: x.relative_path):
            print(f"  {info.relative_path:60s}  {info.size:>10,} bytes")
        return

    if args.output:
        output_dir = args.output
    else:
        output_dir = str(input_path.parent / f"{input_path.stem}_extracted")

    extract_tne_to_dir(
        tne_path,
        output_dir,
        expand_nested=not args.no_nested,
        **decrypt_kwargs,
    )


if __name__ == "__main__":
    main()
