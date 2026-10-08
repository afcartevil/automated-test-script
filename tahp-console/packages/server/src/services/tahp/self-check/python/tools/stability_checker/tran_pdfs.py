#!/usr/bin/env python3
"""
Extract Transsion tdfs partition logs to ./tdfs-<timestamp>/.

Layout (from TranDFSLib.h / stucklogo_dump.h — same on MTK & Qualcomm):
  [stucklogo_header]
  [stucklogo_log_header x TRAN_LOG_INDEX_MAX]
  [payload referenced by log_desc start/end]

Qualcomm differences vs MTK:
  - log_type enum is 0-based: xbl/uefi/abl/kernel/android/hang
  - init sets offset == blksz with reboot_count == 0 (empty is valid)
  - payload for LOG_TYPE_XBL is a raw copy of partition xbl_sc_logs
    (often starts with Qualcomm IMTL + LOG_START text)
"""

from __future__ import annotations

import argparse
import os
import struct
import time
from dataclasses import dataclass
from typing import BinaryIO, List, Tuple

TRAN_DFS_SIG = 0x785690EF
TRAN_LOG_MAGIC = 0xAEE0DEAD  # set when reboot_count reaches TRAN_LOG_INDEX_MAX
TRAN_LOG_INDEX_MAX = 3
TRAN_LOG_TYPE_MAX = 6
TDFS_STUCKLOGO_SIZE = 15 * 1024 * 1024  # QCOM stucklogo region size

# Qualcomm xbl_sc_logs raw image magic (inside LOG_TYPE_XBL payload)
IMTL_MAGIC = b"IMTL"

# MTK: 1-based types used by original tran_pdfs
MTK_FILE_NAMES = (
    "last_pl_lk",  # 1
    "last_pl",  # 2
    "last_kmsg",  # 3
    "last_atf_log",  # 4
    "last_gz_log",  # 5
    "last_kernel",  # 6
    "last_nhang",  # 7
    "last_cpu_hang",  # 8
)

# QCOM: 0-based types from TranDFSLib.h / stucklogo_dump.c
QCOM_FILE_NAMES = {
    0x00: "xbl",
    0x01: "uefi",
    0x02: "abl",
    0x03: "kernel",
    0x04: "android",
    0x05: "hang",
}

HEADER_STRUCT = struct.Struct("<8I")
LOG_DESC_STRUCT = struct.Struct("<3I")
_LOG_HEADER_PREFIX = struct.Struct("<II24sI")
LOG_HEADER_SIZE = _LOG_HEADER_PREFIX.size + TRAN_LOG_TYPE_MAX * LOG_DESC_STRUCT.size


@dataclass
class DfsHeader:
    sig: int
    magic: int
    blksz: int
    partsz: int
    idx: int
    offset: int
    reboot_count: int
    boot_step: int


@dataclass
class LogDesc:
    log_type: int
    start: int
    end: int


@dataclass
class LogHeader:
    log_type: int
    log_cnt: int
    boot_reason: str
    offset: int
    log_desc: List[LogDesc]


def unpack_header(data: bytes) -> DfsHeader:
    if len(data) != HEADER_STRUCT.size:
        raise ValueError("header size mismatch")
    return DfsHeader(*HEADER_STRUCT.unpack(data))


def unpack_log_header(data: bytes) -> LogHeader:
    if len(data) < LOG_HEADER_SIZE:
        raise ValueError("log header size mismatch")
    log_type, log_cnt, boot_reason_b, loff = _LOG_HEADER_PREFIX.unpack_from(data, 0)
    off = _LOG_HEADER_PREFIX.size
    boot_reason = boot_reason_b.split(b"\x00", 1)[0].decode("utf-8", errors="replace")
    descs: List[LogDesc] = []
    for _ in range(TRAN_LOG_TYPE_MAX):
        lt, st, en = LOG_DESC_STRUCT.unpack_from(data, off)
        off += LOG_DESC_STRUCT.size
        descs.append(LogDesc(lt, st, en))
    return LogHeader(log_type, log_cnt, boot_reason, loff, descs)


def detect_platform(header: DfsHeader, fp: BinaryIO) -> str:
    """Heuristic: QCOM stucklogo region is fixed 15MB (TDFS_STUCKLOGO_SIZE)."""
    if header.partsz == TDFS_STUCKLOGO_SIZE:
        return "qcom"
    # leftover xbl_sc_logs image often sits at first data block
    if header.blksz and peek_magic(fp, header.blksz) == IMTL_MAGIC:
        return "qcom"
    return "mtk"


def peek_magic(fp: BinaryIO, offset: int, size: int = 4) -> bytes:
    pos = fp.tell()
    try:
        fp.seek(offset)
        return fp.read(size)
    finally:
        fp.seek(pos)


def dfs_valid(fp: BinaryIO) -> Tuple[DfsHeader, str]:
    raw = fp.read(HEADER_STRUCT.size)
    if len(raw) != HEADER_STRUCT.size:
        print("read dfs header fail!")
        raise ValueError("short dfs header")

    header = unpack_header(raw)
    print(
        "sig:0x{:x} magic:0x{:x} blksz:{}, partsz:{}, idx={}, offset={}, reboot_count={}".format(
            header.sig,
            header.magic,
            header.blksz,
            header.partsz,
            header.idx,
            header.offset,
            header.reboot_count,
        )
    )

    if header.sig != TRAN_DFS_SIG:
        print("dfs invalid!")
        raise ValueError("invalid dfs header sig")

    if header.blksz == 0:
        raise ValueError("invalid blksz")

    # Init state sets offset == blksz with reboot_count == 0 (see tdfs_stucklogo_init_header).
    # After logs are written, offset advances past blksz. Reject only clearly broken values.
    if header.offset > header.partsz:
        print("dfs invalid!")
        raise ValueError("invalid dfs header offset > partsz")
    if header.idx > TRAN_LOG_INDEX_MAX:
        print("dfs invalid!")
        raise ValueError("invalid dfs header idx")

    platform = detect_platform(header, fp)
    print(f"platform: {platform}")

    if header.magic != TRAN_LOG_MAGIC or header.reboot_count < TRAN_LOG_INDEX_MAX:
        print("abormal boot less three times")

    fp.seek(0)
    return header, platform


def read_at(fp: BinaryIO, offset: int, size: int) -> bytes:
    if size < 0:
        raise ValueError(f"negative read size {size}")
    fp.seek(offset)
    data = fp.read(size)
    if len(data) != size:
        raise OSError(f"read expected {size} bytes at offset {offset}, got {len(data)}")
    return data


def ensure_dir(pathname: str) -> None:
    if os.path.isdir(pathname):
        return
    os.makedirs(pathname, mode=0o777, exist_ok=True)
    try:
        os.chmod(pathname, 0o777)
    except OSError:
        pass


def make_outdir() -> str:
    t = time.localtime()
    dirname = "tdfs-{}-{}-{}-{}-{}-{}".format(
        t.tm_year, t.tm_mon, t.tm_mday, t.tm_hour, t.tm_min, t.tm_sec
    )
    path = os.path.join(".", dirname) + os.sep
    ensure_dir(path)
    print(f"path:{path}")
    return path


def write_log_file(subdir: str, name: str, data: bytes) -> None:
    ensure_dir(subdir)
    file_path = os.path.join(subdir, name)
    print(f"\topen {file_path} ({len(data)} bytes)")
    with open(file_path, "wb") as out:
        out.write(data)
    try:
        os.chmod(file_path, 0o666)
    except OSError:
        pass


def log_type_name(platform: str, log_type: int) -> str:
    if platform == "qcom":
        return QCOM_FILE_NAMES.get(log_type, f"unknown_type_{log_type}")
    if log_type < 1 or log_type > len(MTK_FILE_NAMES):
        return f"unknown_type_{log_type}"
    return MTK_FILE_NAMES[log_type - 1]


def save_logs(idx: int, out_base: str, log_desc: LogDesc, fp: BinaryIO, platform: str) -> None:
    size = log_desc.end - log_desc.start
    if size <= 0:
        print(f"skip invalid range start={log_desc.start} end={log_desc.end}")
        return
    name = log_type_name(platform, log_desc.log_type)
    if platform == "qcom":
        name = f"{name}.bin"
    data = read_at(fp, log_desc.start, size)
    write_log_file(os.path.join(out_base, str(idx)), name, data)


def slot_indices(header: DfsHeader) -> List[int]:
    """
    Match stucklogo_dump.c archive order:
      - reboot_count <= 3: slots 0..reboot_count-1
      - reboot_count > 3: slot 0 pinned, then ring [1, TRAN_LOG_INDEX_MAX)
    """
    if header.reboot_count == 0:
        return []
    if header.reboot_count <= TRAN_LOG_INDEX_MAX:
        return list(range(header.reboot_count))

    out = [0]
    ring = TRAN_LOG_INDEX_MAX - 1
    oldest = 1 + (header.idx % ring)
    for i in range(1, TRAN_LOG_INDEX_MAX):
        out.append(1 + ((oldest - 1 + (i - 1)) % ring))
    return out


def parse_stucklogo(header: DfsHeader, fp: BinaryIO, platform: str) -> str:
    """Parse official stucklogo descriptors. Returns output directory path."""
    print(f"log write cursor=0x{header.offset:x}")
    path = make_outdir()
    base = path.rstrip(os.sep)

    indices = slot_indices(header)
    if not indices:
        print("reboot_count=0: no stucklogo snapshots (header initialized / cleaned)")
        return path

    buf = read_at(fp, HEADER_STRUCT.size, TRAN_LOG_INDEX_MAX * LOG_HEADER_SIZE)

    for out_i, slot in enumerate(indices):
        chunk = buf[slot * LOG_HEADER_SIZE : (slot + 1) * LOG_HEADER_SIZE]
        lh = unpack_log_header(chunk)
        cnt = min(lh.log_cnt, TRAN_LOG_TYPE_MAX)
        print("-----------------")
        print(
            f"slot:{slot} -> dir:{out_i}, logtype:0x{lh.log_type:x}, "
            f"reason:{lh.boot_reason}, log_count:{cnt}"
        )
        for j in range(cnt):
            d = lh.log_desc[j]
            print(
                f"logdesc: type:0x{d.log_type:x}({log_type_name(platform, d.log_type)}), "
                f"start:{d.start}, end:{d.end}"
            )
            save_logs(out_i, base, d, fp, platform)
        if cnt == 0:
            print("(empty slot)")
        print("-----------------")
    return path


def stucklogo_has_type(header: DfsHeader, fp: BinaryIO, log_type: int) -> bool:
    if header.reboot_count == 0:
        return False
    buf = read_at(fp, HEADER_STRUCT.size, TRAN_LOG_INDEX_MAX * LOG_HEADER_SIZE)
    for slot in range(min(header.reboot_count, TRAN_LOG_INDEX_MAX)):
        lh = unpack_log_header(buf[slot * LOG_HEADER_SIZE : (slot + 1) * LOG_HEADER_SIZE])
        for j in range(min(lh.log_cnt, TRAN_LOG_TYPE_MAX)):
            if lh.log_desc[j].log_type == log_type and lh.log_desc[j].end > lh.log_desc[j].start:
                return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Extract Transsion tdfs stucklogo logs (MTK + Qualcomm)."
    )
    ap.add_argument(
        "tdfs",
        nargs="?",
        default="tdfs",
        help="Path to tdfs dump or block device (default: ./tdfs)",
    )
    ap.add_argument(
        "--platform",
        choices=("auto", "mtk", "qcom"),
        default="auto",
        help="Force platform log-type naming (default: auto-detect)",
    )
    args = ap.parse_args()

    try:
        with open(args.tdfs, "rb") as fp:
            header, platform = dfs_valid(fp)
            if args.platform != "auto":
                platform = args.platform
                print(f"platform overridden: {platform}")

            parse_stucklogo(header, fp, platform)

            if platform == "qcom" and not stucklogo_has_type(header, fp, 0x03):
                print(
                    "note: stucklogo has no LOG_TYPE_KERNEL — "
                    "kernel log was not written into stucklogo descriptors"
                )

    except FileNotFoundError:
        print("dfs file not exist!")
        print("tran_pdfs failed")
        return 1
    except OSError as e:
        print(f"open dfs file error = {e}!")
        print("tran_pdfs failed")
        return 1
    except (ValueError, struct.error) as e:
        print(f"parse error: {e}")
        print("tran_pdfs failed")
        return 1

    print("tran_pdfs success!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
