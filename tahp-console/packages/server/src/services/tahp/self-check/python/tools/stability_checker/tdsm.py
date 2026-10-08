#!/usr/bin/env python3
"""
Python port of tdsm.c — parse Transsion device messages (TDSM).

Layouts:
  MTK:  TDSM at expdb tail
        base = file_size - EXPDB_RESERVED_SIZE + EXPDB_MRDUMP_CONFIG_RESERVED_SIZE
  QCOM: TDSM at fixed offset in tdfs partition (TranDSMLib.h)
        base = TDSM_LOG_PARTITION_OFFSET (0x2D00000)
"""

from __future__ import annotations

import argparse
import os
import struct
from dataclasses import dataclass
from typing import BinaryIO, Optional, Tuple

# Must match tdsm.h / TranDSMLib.h
TRAN_DEVMSG_MAGIC = b"TDSM"
EXPDB_RESERVED_SIZE = 0x300000
EXPDB_MRDUMP_CONFIG_RESERVED_SIZE = 0x100
TRAN_DEVMSG_RESERVED_SIZE = 0xFFF00
TRAN_DEVMSG_MAX_SIZE = 256  # desc.len upper bound for parse (msg payload is smaller)
TRAN_DEVMSG_MAX_LEN = 300
# QCOM: AEE_IPANIC_PLABLE "tdfs" + TDSM_LOG_PARTITION_OFFSET
TDSM_LOG_PARTITION_OFFSET = 0x2D00000

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


def mtk_header_base(file_size: int) -> int:
    return file_size - EXPDB_RESERVED_SIZE + EXPDB_MRDUMP_CONFIG_RESERVED_SIZE


def read_header_at(fp: BinaryIO, base: int) -> Optional[TranDevmsgHeader]:
    if base < 0:
        return None
    fp.seek(0, os.SEEK_END)
    if base + HEADER_STRUCT.size > fp.tell():
        return None
    fp.seek(base)
    raw = fp.read(HEADER_STRUCT.size)
    if len(raw) != HEADER_STRUCT.size:
        return None
    header = unpack_header(raw)
    if header.magic[:4] != TRAN_DEVMSG_MAGIC:
        return None
    return header


def header_fields_ok(header: TranDevmsgHeader) -> bool:
    header_sz = HEADER_STRUCT.size
    return (
        header.offset > header_sz
        and header.offset <= TRAN_DEVMSG_RESERVED_SIZE
        and header.count != 0
    )


def detect_tdsm_base(fp: BinaryIO, platform: str) -> Tuple[str, int, TranDevmsgHeader]:
    """
    Locate TDSM header. Returns (platform, base_offset, header).
    platform: "mtk" | "qcom" (forced or auto-detected).
    """
    fp.seek(0, os.SEEK_END)
    file_size = fp.tell()

    candidates: list[Tuple[str, int]] = []
    if platform in ("auto", "qcom"):
        candidates.append(("qcom", TDSM_LOG_PARTITION_OFFSET))
    if platform in ("auto", "mtk"):
        candidates.append(("mtk", mtk_header_base(file_size)))

    for plat, base in candidates:
        header = read_header_at(fp, base)
        if header is None:
            continue
        if not header_fields_ok(header):
            print(
                f"tdsm@{base:#x} ({plat}): magic ok but bad offset/count "
                f"(offset=0x{header.offset:x} count=0x{header.count:x})"
            )
            continue
        return plat, base, header

    raise ValueError(
        "TDSM header not found "
        f"(tried platform={platform}; qcom@{TDSM_LOG_PARTITION_OFFSET:#x}, "
        f"mtk@expdb_tail)"
    )


def check_tdsm_valid(
    fp: BinaryIO, path: str, platform: str = "auto"
) -> Tuple[str, TranDevmsgHeader, int]:
    fp.seek(0, os.SEEK_END)
    file_size = fp.tell()
    if file_size < 0:
        raise OSError("could not stat file")

    print(f"check_tdsm_valid: open {path} file success, fileSize = {file_size}")

    plat, base, header = detect_tdsm_base(fp, platform)
    magic_show = header.magic[:4].decode("ascii", errors="replace")
    print(f"platform: {plat}  tdsm_base: 0x{base:x}")
    print(
        "header: magic={}, offset=0x{:x}, reboot_count=0x{:x}, count=0x{:x}".format(
            magic_show,
            header.offset,
            header.reboot_count,
            header.count,
        )
    )

    data_offset = base + HEADER_STRUCT.size
    return plat, header, data_offset


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
        description="Parse Transsion TDSM (MTK expdb tail / QCOM tdfs@0x2D00000).",
    )
    ap.add_argument(
        "image",
        nargs="?",
        default="tdfs",
        help="Path to expdb (MTK) or tdfs (QCOM) image (default: ./tdfs)",
    )
    ap.add_argument(
        "--platform",
        choices=("auto", "mtk", "qcom"),
        default="auto",
        help="Force layout: mtk=expdb tail, qcom=tdfs@0x2D00000 (default: auto)",
    )
    args = ap.parse_args()
    path = args.image

    try:
        with open(path, "rb") as fp:
            _plat, header, data_off = check_tdsm_valid(fp, path, args.platform)
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
