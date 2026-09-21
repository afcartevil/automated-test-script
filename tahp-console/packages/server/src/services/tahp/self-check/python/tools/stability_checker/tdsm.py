#!/usr/bin/env python3
"""
Python port of tdsm.c — read Transsion device messages from the tail of expdb.
"""

from __future__ import annotations

import argparse
import os
import struct
from dataclasses import dataclass
from typing import BinaryIO

# Must match tdsm.h
TRAN_DEVMSG_MAGIC = b"TDSM"
EXPDB_RESERVED_SIZE = 0x300000
EXPDB_MRDUMP_CONFIG_RESERVED_SIZE = 0x100
TRAN_DEVMSG_RESERVED_SIZE = 0xFFF00
TRAN_DEVMSG_MAX_SIZE = 256
TRAN_DEVMSG_MAX_LEN = 300

# sizeof(struct tran_devmsg_header): magic[4] + u32 * 3
HEADER_STRUCT = struct.Struct("<4sIII")
# id, phase as u32 (enum int); type, idx, start, len; rtc_time 6xu16; reserved u32
# Matches typical GCC ARM/Android: enums are 4 bytes.
DESC_STRUCT = struct.Struct("<IIIIII6HI")  # 40 bytes (enums as 32-bit)


@dataclass
class TranDevmsgHeader:
    magic: bytes
    offset: int
    reboot_count: int
    count: int


@dataclass
class TranDevmsgDesc:
    id: int
    phase: int
    type: int
    idx: int
    start: int
    length: int
    tm_sec: int
    tm_min: int
    tm_hour: int
    tm_mday: int
    tm_mon: int
    tm_year: int
    reserved: int


def unpack_header(data: bytes) -> TranDevmsgHeader:
    if len(data) != HEADER_STRUCT.size:
        raise ValueError("devmsg header size mismatch")
    magic, offset, reboot_count, count = HEADER_STRUCT.unpack(data)
    return TranDevmsgHeader(magic, offset, reboot_count, count)


def unpack_desc(data: bytes) -> TranDevmsgDesc:
    if len(data) != DESC_STRUCT.size:
        raise ValueError("devmsg desc size mismatch")
    (
        eid,
        phase,
        mtype,
        idx,
        start,
        length,
        tm_sec,
        tm_min,
        tm_hour,
        tm_mday,
        tm_mon,
        tm_year,
        reserved,
    ) = DESC_STRUCT.unpack(data)
    return TranDevmsgDesc(
        eid,
        phase,
        mtype,
        idx,
        start,
        length,
        tm_sec,
        tm_min,
        tm_hour,
        tm_mday,
        tm_mon,
        tm_year,
        reserved,
    )


def header_base_offset(file_size: int) -> int:
    return file_size - EXPDB_RESERVED_SIZE + EXPDB_MRDUMP_CONFIG_RESERVED_SIZE


def check_tdsm_valid(fp: BinaryIO, path: str) -> tuple[TranDevmsgHeader, int]:
    file_size = fp.seek(0, os.SEEK_END)
    if file_size < 0:
        raise OSError("could not stat file")

    base = header_base_offset(file_size)
    if base < 0:
        raise ValueError(
            f"file too small ({file_size}) for expdb tail layout (need >= {EXPDB_RESERVED_SIZE - EXPDB_MRDUMP_CONFIG_RESERVED_SIZE})"
        )

    print(f"check_tdsm_valid: open {path} file success, fileSize = {file_size}")

    fp.seek(base)
    raw = fp.read(HEADER_STRUCT.size)
    if len(raw) != HEADER_STRUCT.size:
        print(f"check_tdsm_valid: read devmsg header fail, ret = {len(raw)}")
        raise ValueError("short header")

    header = unpack_header(raw)
    magic_show = header.magic[:4].decode("ascii", errors="replace")
    print(
        "header: magic={}, offset=0x{:x}, reboot_count=0x{:x}, count=0x{:x}".format(
            magic_show,
            header.offset,
            header.reboot_count,
            header.count,
        )
    )

    if header.magic[:4] != TRAN_DEVMSG_MAGIC:
        print("devmsg header invalid!")
        raise ValueError("bad magic")
    header_sz = HEADER_STRUCT.size
    if (
        header.offset <= header_sz
        or header.offset > TRAN_DEVMSG_RESERVED_SIZE
        or not header.count
    ):
        print("devmsg header invalid!")
        raise ValueError("bad offset or count")

    data_offset = base + header_sz
    return header, data_offset


def parse_tdsm(fp: BinaryIO, header: TranDevmsgHeader, start_offset: int) -> None:
    offset = start_offset
    desc_sz = DESC_STRUCT.size

    for i in range(header.count):
        fp.seek(offset)
        desc_raw = fp.read(desc_sz)
        if len(desc_raw) != desc_sz:
            print(f"parse_tdsm: read devmsg desc fail, ret = {len(desc_raw)}")
            raise ValueError("short desc")

        desc = unpack_desc(desc_raw)

        head = "<{}, {}, {}, {}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}>".format(
            desc.id,
            desc.type,
            desc.length,
            desc.tm_year,
            desc.tm_mon,
            desc.tm_mday,
            desc.tm_hour,
            desc.tm_min,
            desc.tm_sec,
        )

        offset += desc_sz
        fp.seek(offset)

        if desc.length > TRAN_DEVMSG_MAX_SIZE:
            raise ValueError(
                f"parse_tdsm: devmsg{i} size 0x{desc.length:x} exceed max size 0x{TRAN_DEVMSG_MAX_SIZE:x}"
            )

        payload_len = desc.length - desc_sz
        if payload_len < 0:
            raise ValueError(f"devmsg{i}: len {desc.length} smaller than desc size")

        msg_raw = fp.read(payload_len)
        if len(msg_raw) != payload_len:
            print(f"parse_tdsm: read devmsg buf fail, ret = {len(msg_raw)}")
            raise ValueError("short msg")

        # Match strncat + printf("%s"): C string ends at first NUL in appended payload / buffer.
        raw_line = head.encode("utf-8", errors="replace") + msg_raw
        z = raw_line.find(b"\x00")
        if z >= 0:
            raw_line = raw_line[:z]
        line = raw_line.decode("utf-8", errors="replace")
        if len(line) > TRAN_DEVMSG_MAX_LEN:
            line = line[:TRAN_DEVMSG_MAX_LEN]
        print(line)

        offset += payload_len


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Parse Transsion expdb devmsg region (tdsm.c port).",
    )
    ap.add_argument(
        "expdb",
        nargs="?",
        default="expdb",
        help="Path to expdb image or device (default: ./expdb)",
    )
    args = ap.parse_args()
    path = args.expdb

    try:
        with open(path, "rb") as fp:
            header, data_off = check_tdsm_valid(fp, path)
            parse_tdsm(fp, header, data_off)
    except FileNotFoundError:
        print(f"check_tdsm_valid: file {path} not exist!")
        print("parse tdsm failed")
        return 1
    except OSError as e:
        err = getattr(e, "strerror", None) or str(e)
        print(f"check_tdsm_valid: open {path} file error = {err}!")
        print("parse tdsm failed")
        return 1
    except (ValueError, struct.error) as e:
        print(f"parse error: {e}")
        print("parse tdsm failed")
        return 1

    print("parse tdsm success!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
