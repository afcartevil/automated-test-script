#!/usr/bin/env python3
"""
Python port of tran_pdfs.c — extract Transsion DFS (tdfs) partition logs to ./tdfs-<timestamp>/.
"""

from __future__ import annotations

import argparse
import os
import struct
import time
from dataclasses import dataclass
from typing import BinaryIO, List

# Must match tran_pdfs.h
TRAN_DFS_SIG = 0x785690EF
TRAN_LOG_MAGIC = 0xAEE0DEAD
TRAN_LOG_INDEX_MAX = 3
TRAN_LOG_TYPE_MAX = 6
LOG_MAX = 3

FILE_NAMES = (
    "last_pl_lk",  # LOG_PLLK = 1
    "last_pl",
    "last_kmsg",
    "last_atf_log",
    "last_gz_log",
    "last_kernel",
    "last_nhang",
    "last_cpu_hang",
)

HEADER_STRUCT = struct.Struct("<8I")  # sig, magic, blksz, partsz, idx, offset, reboot_count, boot_step
LOG_DESC_STRUCT = struct.Struct("<3I")  # log_type, start, end
# log_type, log_cnt, boot_reason[24], offset, then TRAN_LOG_TYPE_MAX log_desc
_LOG_HEADER_PREFIX = struct.Struct("<II24sI")


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
    fields = HEADER_STRUCT.unpack(data)
    return DfsHeader(*fields)


def unpack_log_header(data: bytes) -> LogHeader:
    need = _LOG_HEADER_PREFIX.size + TRAN_LOG_TYPE_MAX * LOG_DESC_STRUCT.size
    if len(data) < need:
        raise ValueError("log header size mismatch")
    off = 0
    log_type, log_cnt, boot_reason_b, loff = _LOG_HEADER_PREFIX.unpack_from(data, off)
    off += _LOG_HEADER_PREFIX.size
    boot_reason = boot_reason_b.split(b"\x00", 1)[0].decode("utf-8", errors="replace")
    descs: List[LogDesc] = []
    for _ in range(TRAN_LOG_TYPE_MAX):
        lt, st, en = LOG_DESC_STRUCT.unpack_from(data, off)
        off += LOG_DESC_STRUCT.size
        descs.append(LogDesc(lt, st, en))
    return LogHeader(log_type, log_cnt, boot_reason, loff, descs)


def dfs_valid(fp: BinaryIO) -> DfsHeader:
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

    if (
        header.sig != TRAN_DFS_SIG
        or header.offset <= header.blksz
        or header.offset > header.partsz
        or header.idx > TRAN_LOG_INDEX_MAX
    ):
        print("dfs invalid!")
        raise ValueError("invalid dfs header")

    if header.magic != TRAN_LOG_MAGIC or header.reboot_count <= 3:
        print("abormal boot less three times")

    fp.seek(0)
    return header


def read_at(fp: BinaryIO, offset: int, size: int) -> bytes:
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


def save_logs(idx: int, out_base: str, log_desc: LogDesc, fp: BinaryIO) -> None:
    file_size = log_desc.end - log_desc.start
    if file_size < 0:
        print(f"invalid range start={log_desc.start} end={log_desc.end}")
        raise ValueError("negative log size")

    subdir = os.path.join(out_base, str(idx))
    ensure_dir(subdir)

    lt = log_desc.log_type
    if lt < 1 or lt > len(FILE_NAMES):
        name = f"unknown_type_{lt}"
    else:
        name = FILE_NAMES[lt - 1]

    file_path = os.path.join(subdir, name)
    print(f"	open {file_path}")

    data = read_at(fp, log_desc.start, file_size)
    with open(file_path, "wb") as out:
        os.chmod(file_path, 0o666)
        out.write(data)


def parse_dfs(header: DfsHeader, fp: BinaryIO) -> None:
    maxsize = header.offset
    print(f"log maxsize=0x{maxsize:x}")

    log_header_size = TRAN_LOG_TYPE_MAX * LOG_DESC_STRUCT.size + _LOG_HEADER_PREFIX.size
    one_log_header = log_header_size  # same as sizeof one struct in C

    total_headers = header.reboot_count * one_log_header
    buf = read_at(fp, HEADER_STRUCT.size, total_headers)

    t = time.localtime()
    dirname = "tdfs-{}-{}-{}-{}-{}-{}".format(
        t.tm_year,
        t.tm_mon,
        t.tm_mday,
        t.tm_hour,
        t.tm_min,
        t.tm_sec,
    )
    path = os.path.join(".", dirname) + os.sep
    ensure_dir(path)
    print(f"path:{path}")

    if header.reboot_count > LOG_MAX:
        log_count = LOG_MAX
    else:
        log_count = header.reboot_count

    for i in range(log_count):
        chunk = buf[i * one_log_header : (i + 1) * one_log_header]
        lh = unpack_log_header(chunk)
        print("-----------------")
        print(
            f"logtype:{lh.log_type:x}, reason:{lh.boot_reason}, log_count:{lh.log_cnt}"
        )
        for j in range(lh.log_cnt):
            d = lh.log_desc[j]
            print(f"logdesc: logtype:{d.log_type:x}, start:{d.start}, end:{d.end}")
            save_logs(i, path.rstrip(os.sep), d, fp)
        print("-----------------")


def main() -> int:
    ap = argparse.ArgumentParser(description="Extract Transsion tdfs partition logs (tran_pdfs.c port).")
    ap.add_argument(
        "tdfs",
        nargs="?",
        default="tdfs",
        help="Path to tdfs dump or block device (default: ./tdfs)",
    )
    args = ap.parse_args()
    tdfs_path = args.tdfs

    try:
        with open(tdfs_path, "rb") as fp:
            header = dfs_valid(fp)
            parse_dfs(header, fp)
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
