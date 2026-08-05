"""游戏场景 networklog/.cap 解析库。

依赖主机 Wireshark CLI：`capinfos`（必选）、`tshark`（--deep 时使用）。
复用 base_wifi_data/scripts/wireshark_cli.py 做工具发现。
"""

from __future__ import annotations

import csv
import io
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

_CAP_NAME_TS_RE = re.compile(
    r"(?P<y>\d{4})_(?P<m>\d{2})(?P<d>\d{2})_(?P<H>\d{2})(?P<M>\d{2})(?P<S>\d{2})",
)
_PCAP_MAGIC_LE = b"\xd4\xc3\xb2\xa1"
_PCAP_MAGIC_BE = b"\xa1\xb2\xc3\xd4"
_PCAPNG_MAGIC = b"\x0a\x0d\x0d\x0a"


def _wireshark_scripts_dir() -> Path:
    # .../domain/power/flow/game/game_network/scripts
    # -> .../domain/power/base/wifi_data/scripts
    return Path(__file__).resolve().parents[4] / "base" / "wifi_data" / "scripts"


def _import_wireshark_cli():
    import sys

    ws = str(_wireshark_scripts_dir())
    if ws not in sys.path:
        sys.path.insert(0, ws)
    from wireshark_cli import (  # type: ignore
        configure_wireshark_cli,
        resolve_command_path,
        wireshark_cli_preflight,
    )

    return configure_wireshark_cli, resolve_command_path, wireshark_cli_preflight


def discover_cap_files(root: Path, *, include_tmp: bool = False) -> list[Path]:
    """递归发现 .cap；默认跳过 .cap.tmp* 未完成抓包。"""
    root = Path(root)
    if root.is_file() and root.suffix.lower() == ".cap":
        return [root]
    if not root.is_dir():
        return []
    found: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        name = path.name.lower()
        if name.endswith(".cap"):
            found.append(path)
        elif include_tmp and ".cap.tmp" in name:
            found.append(path)
    return sorted(found, key=lambda p: p.as_posix().lower())


def resolve_networklog_roots(hint: Path) -> list[Path]:
    """从 mobilelog/APLog、设备 downloads 根或 networklog 本身解析 cap 根目录。"""
    hint = Path(hint).resolve()
    candidates: list[Path] = []

    def _add(p: Path) -> None:
        if p.is_dir() and p not in candidates:
            candidates.append(p)

    if hint.is_file() and hint.suffix.lower() == ".cap":
        _add(hint.parent)
        return candidates

    _add(hint)
    # .../mobilelog/APLog_* -> 上两级 networklog
    if hint.name.lower().startswith("aplog"):
        device_root = hint.parent.parent  # mobilelog -> device
        _add(device_root / "networklog")
    # .../mobilelog -> 同级 networklog
    if hint.name.lower() == "mobilelog":
        _add(hint.parent / "networklog")
    # converted 扁平 NTLog
    parts = list(hint.parts)
    lower = [p.lower() for p in parts]
    if "converted" in lower:
        idx = lower.index("converted")
        _add(Path(*parts[: idx + 1]) / "NTLog")
    # downloads/<sn>/<sn>/networklog
    if hint.name.lower() == "networklog":
        _add(hint)
    elif (hint / "networklog").is_dir():
        _add(hint / "networklog")
    elif (hint / "netlog").is_dir():
        _add(hint / "netlog")

    # 若 hint 下直接有 cap，保留
    return candidates or [hint]


def filename_start_hint(path: Path) -> str | None:
    m = _CAP_NAME_TS_RE.search(path.name)
    if not m:
        return None
    return (
        f"{m.group('y')}-{m.group('m')}-{m.group('d')} "
        f"{m.group('H')}:{m.group('M')}:{m.group('S')}"
    )


def _parse_capinfos_time(raw: str) -> datetime | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    for fmt in (
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f %Z",
    ):
        try:
            return datetime.strptime(raw.replace(" CST", "").replace(" UTC", ""), fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _run(cmd: list[str], *, timeout_s: int = 120) -> tuple[int, str, str]:
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_s,
        check=False,
    )
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def sniff_pcap_header(path: Path) -> dict[str, Any]:
    """不依赖 tshark 的轻量文件头探测。"""
    out: dict[str, Any] = {
        "path": str(path),
        "size_bytes": path.stat().st_size if path.is_file() else 0,
        "format": "unknown",
    }
    try:
        magic = path.read_bytes()[:4]
    except OSError as exc:
        out["error"] = str(exc)
        return out
    if magic == _PCAP_MAGIC_LE:
        out["format"] = "pcap_le"
    elif magic == _PCAP_MAGIC_BE:
        out["format"] = "pcap_be"
    elif magic == _PCAPNG_MAGIC:
        out["format"] = "pcapng"
    return out


def parse_cap_with_capinfos(
    path: Path,
    *,
    capinfos: str,
) -> dict[str, Any]:
    """用 capinfos 提取包数/起止时间/时长等摘要。"""
    base = sniff_pcap_header(path)
    # -Tm CSV header+row; fields: name type packets duration start end bytes/s
    code, stdout, stderr = _run(
        [
            capinfos,
            "-Tm",
            "-c",  # packets
            "-u",  # duration
            "-a",  # start
            "-e",  # end
            "-y",  # data byte rate
            "-i",  # average packet rate
            "-z",  # average packet size
            str(path),
        ],
        timeout_s=180,
    )
    row: dict[str, Any] = {
        **base,
        "tool": "capinfos",
        "filename_start_hint": filename_start_hint(path),
    }
    if code != 0:
        row["error"] = (stderr or stdout or f"capinfos exit {code}")[:500]
        return row

    reader = csv.DictReader(io.StringIO(stdout))
    records = list(reader)
    if not records:
        row["error"] = "capinfos 无表格输出"
        row["raw"] = stdout[:500]
        return row
    rec = records[0]

    def _get(*keys: str) -> str:
        for k in keys:
            if k in rec and rec[k] not in (None, ""):
                return str(rec[k]).strip()
        # case-insensitive fallback
        lower = {str(a).lower(): b for a, b in rec.items()}
        for k in keys:
            if k.lower() in lower and lower[k.lower()] not in (None, ""):
                return str(lower[k.lower()]).strip()
        return ""

    packets_s = _get("Number of packets", "Packets")
    duration_s = _get("Capture duration (seconds)", "Capture duration")
    start_s = _get("Start time", "First packet time")
    end_s = _get("End time", "Last packet time")
    byte_rate_s = _get("Data byte rate (bytes/sec)", "Data byte rate")
    pkt_rate_s = _get("Average packet rate (packets/sec)", "Average packet rate")
    avg_size_s = _get("Average packet size (bytes)", "Average packet size")

    try:
        packets = int(float(packets_s)) if packets_s else None
    except ValueError:
        packets = None
    try:
        duration = float(duration_s) if duration_s else None
    except ValueError:
        duration = None

    start_dt = _parse_capinfos_time(start_s)
    end_dt = _parse_capinfos_time(end_s)
    row.update(
        {
            "packets": packets,
            "duration_seconds": duration,
            "start_time": start_dt.isoformat(sep=" ", timespec="milliseconds")
            if start_dt
            else (start_s or None),
            "end_time": end_dt.isoformat(sep=" ", timespec="milliseconds")
            if end_dt
            else (end_s or None),
            "start_dt": start_dt,
            "end_dt": end_dt,
            "data_byte_rate": float(byte_rate_s) if byte_rate_s else None,
            "avg_packet_rate": float(pkt_rate_s) if pkt_rate_s else None,
            "avg_packet_size": float(avg_size_s) if avg_size_s else None,
            "file_type": _get("File type"),
        }
    )
    return row


def _overlap_seconds(
    a0: datetime | None,
    a1: datetime | None,
    b0: datetime | None,
    b1: datetime | None,
) -> float | None:
    if not (a0 and a1 and b0 and b1):
        return None
    lo = max(a0, b0)
    hi = min(a1, b1)
    return max(0.0, (hi - lo).total_seconds())


def deep_protocol_summary(
    path: Path,
    *,
    tshark: str,
    start: datetime | None = None,
    end: datetime | None = None,
    timeout_s: int = 300,
) -> dict[str, Any]:
    """tshark 协议树摘要（可选时间窗；大文件可能较慢）。"""
    display_filter = None
    if start and end:
        display_filter = (
            f"frame.time_epoch>={start.timestamp()} && "
            f"frame.time_epoch<={end.timestamp()}"
        )
    # -z io,phs[,filter]：filter 需写在统计项内，单靠 -Y 可能不生效
    zopt = f"io,phs,{display_filter}" if display_filter else "io,phs"
    cmd = [tshark, "-r", str(path), "-q", "-z", zopt]
    code, stdout, stderr = _run(cmd, timeout_s=timeout_s)
    out: dict[str, Any] = {
        "ok": code == 0,
        "display_filter": display_filter,
    }
    if code != 0:
        out["error"] = (stderr or stdout or f"tshark exit {code}")[:800]
        return out
    lines = [ln.rstrip() for ln in stdout.splitlines() if ln.strip()]
    out["protocol_hierarchy_text"] = "\n".join(lines[:80])
    return out


def deep_ip_conversations(
    path: Path,
    *,
    tshark: str,
    start: datetime | None = None,
    end: datetime | None = None,
    top_n: int = 15,
    timeout_s: int = 300,
) -> dict[str, Any]:
    display_filter = None
    if start and end:
        display_filter = (
            f"frame.time_epoch>={start.timestamp()} && "
            f"frame.time_epoch<={end.timestamp()}"
        )
    zopt = f"conv,ip,{display_filter}" if display_filter else "conv,ip"
    cmd = [tshark, "-r", str(path), "-q", "-z", zopt]
    code, stdout, stderr = _run(cmd, timeout_s=timeout_s)
    out: dict[str, Any] = {"ok": code == 0, "display_filter": display_filter}
    if code != 0:
        out["error"] = (stderr or stdout or f"tshark exit {code}")[:800]
        return out
    rows: list[str] = []
    for ln in stdout.splitlines():
        s = ln.strip()
        if not s or s.startswith("=") or s.startswith("Filter") or s.startswith("IPv4"):
            continue
        if "<->" in s or "↔" in s:
            rows.append(s)
    out["conversations"] = rows[:top_n]
    out["conversation_count_listed"] = len(rows[:top_n])
    return out


def deep_interface_traffic(
    path: Path,
    *,
    tshark: str,
    start: datetime | None = None,
    end: datetime | None = None,
    max_packets: int = 0,
    timeout_s: int = 600,
) -> dict[str, Any]:
    """统计 T_game 窗内接口索引与本地 IP（SLL ifindex / 私网地址）。"""
    cmd = [
        tshark,
        "-r",
        str(path),
        "-T",
        "fields",
        "-e",
        "sll.ifindex",
        "-e",
        "frame.interface_id",
        "-e",
        "ip.src",
        "-e",
        "ip.dst",
    ]
    if start and end:
        cmd.extend(
            [
                "-Y",
                f"frame.time_epoch>={start.timestamp()} && "
                f"frame.time_epoch<={end.timestamp()}",
            ]
        )
    if max_packets and max_packets > 0:
        cmd.extend(["-c", str(max_packets)])
    code, stdout, stderr = _run(cmd, timeout_s=timeout_s)
    out: dict[str, Any] = {"ok": code == 0}
    if code != 0:
        out["error"] = (stderr or stdout or f"tshark exit {code}")[:800]
        return out

    from collections import Counter

    ifaces: Counter[str] = Counter()
    local_ips: Counter[str] = Counter()
    pkt_n = 0
    for ln in stdout.splitlines():
        parts = ln.split("\t")
        if len(parts) < 2:
            continue
        pkt_n += 1
        ifindex = (parts[0] or "").strip() or (parts[1].strip() if len(parts) > 1 else "")
        # fields: sll.ifindex, frame.interface_id, ip.src, ip.dst
        sll = (parts[0] or "").strip()
        iface_id = (parts[1] or "").strip() if len(parts) > 1 else ""
        key = sll or iface_id or "?"
        ifaces[key] += 1
        for ip in parts[2:4]:
            ip = (ip or "").strip()
            if not ip:
                continue
            # 多值字段偶发逗号拼接，取首个
            ip0 = ip.split(",")[0].strip()
            if _is_local_ip(ip0):
                local_ips[ip0] += 1

    out["packet_count_in_window"] = pkt_n
    out["interface_index_counts"] = dict(ifaces.most_common(20))
    out["local_ip_counts"] = dict(local_ips.most_common(30))
    out["distinct_interface_indexes"] = sorted(ifaces.keys(), key=lambda k: (-ifaces[k], k))
    out["distinct_local_ips"] = sorted(local_ips.keys(), key=lambda k: (-local_ips[k], k))
    return out


def _is_local_ip(ip: str) -> bool:
    if not ip or "." not in ip:
        return False
    try:
        a, b, *_ = (int(x) for x in ip.split("."))
    except ValueError:
        return False
    if a == 10:
        return True
    if a == 192 and b == 168:
        return True
    if a == 172 and 16 <= b <= 31:
        return True
    # 运营商/共享地址常见于蜂窝
    if a == 100 and 64 <= b <= 127:
        return True
    if a == 11:  # 部分机型 rmnet 私网
        return True
    return False


def _classify_local_ip(ip: str) -> str:
    """粗分本地地址族：wifi_like / cellular_like / other_private。"""
    try:
        a, b, *_ = (int(x) for x in ip.split("."))
    except ValueError:
        return "other"
    if a == 100 and 64 <= b <= 127:
        return "cellular_like"
    if a == 11:
        return "cellular_like"
    if a == 10 or (a == 192 and b == 168) or (a == 172 and 16 <= b <= 31):
        return "wifi_or_lan_like"
    return "other_private"


def judge_dual_channel_from_caps(parsed_files: list[dict[str, Any]]) -> dict[str, Any]:
    """基于重叠 cap 的接口/本地 IP 判定是否双通道。"""
    iface_all: dict[str, int] = {}
    ip_all: dict[str, int] = {}
    families: dict[str, int] = {}
    evidence: list[str] = []
    pkt_total = 0

    for f in parsed_files:
        traffic = f.get("interface_traffic") if isinstance(f.get("interface_traffic"), dict) else {}
        if not traffic.get("ok"):
            continue
        pkt_total += int(traffic.get("packet_count_in_window") or 0)
        for k, v in (traffic.get("interface_index_counts") or {}).items():
            iface_all[k] = iface_all.get(k, 0) + int(v)
        for k, v in (traffic.get("local_ip_counts") or {}).items():
            ip_all[k] = ip_all.get(k, 0) + int(v)
            fam = _classify_local_ip(str(k))
            families[fam] = families.get(fam, 0) + int(v)

    n_iface = len([k for k in iface_all if k and k != "?"])
    n_ip = len(ip_all)
    has_wifi_like = families.get("wifi_or_lan_like", 0) > 0
    has_cell_like = families.get("cellular_like", 0) > 0

    if pkt_total <= 0:
        verdict = "unknown"
        summary = "T_game 重叠 cap 内无有效 IP 包，无法做双通道判定"
    elif n_iface >= 2 and has_wifi_like and has_cell_like:
        verdict = "yes"
        summary = (
            f"检测到 ≥2 个接口索引且同时存在 WiFi/LAN 类与蜂窝类本地地址 → 疑似双通道"
        )
    elif n_iface >= 2:
        verdict = "suspect_multi_iface"
        summary = (
            f"T_game 内出现 {n_iface} 个接口索引，但地址族未同时覆盖 WiFi+蜂窝特征"
        )
    elif has_wifi_like and has_cell_like and n_ip >= 2:
        verdict = "suspect_multi_ip"
        summary = "单接口但本地 IP 同时含 WiFi/LAN 与蜂窝特征地址 → 疑似双通道/切换"
    elif n_iface <= 1 and n_ip <= 1:
        verdict = "no"
        summary = "T_game 重叠抓包基本为单接口、单本地 IP → 非双通道（单通道）"
    else:
        verdict = "no"
        summary = (
            f"单主接口（ifaces={n_iface}）本地 IP={n_ip}，"
            f"未同时满足 WiFi+蜂窝双族特征 → 倾向非双通道"
        )

    if iface_all:
        top_if = sorted(iface_all.items(), key=lambda kv: -kv[1])[:5]
        evidence.append("接口索引: " + ", ".join(f"{k}×{v}" for k, v in top_if))
    if ip_all:
        top_ip = sorted(ip_all.items(), key=lambda kv: -kv[1])[:8]
        evidence.append("本地IP: " + ", ".join(f"{k}×{v}" for k, v in top_ip))
    if families:
        evidence.append(
            "地址族: "
            + ", ".join(f"{k}={v}" for k, v in sorted(families.items(), key=lambda kv: -kv[1]))
        )

    return {
        "verdict": verdict,
        "is_dual_channel": verdict == "yes",
        "summary": summary,
        "packet_count_in_window": pkt_total,
        "interface_index_counts": dict(
            sorted(iface_all.items(), key=lambda kv: (-kv[1], kv[0]))
        ),
        "local_ip_counts": dict(sorted(ip_all.items(), key=lambda kv: (-kv[1], kv[0]))),
        "address_family_counts": families,
        "evidence": evidence,
        "note": (
            "抓包为 Linux SLL 时用 sll.ifindex；"
            "蜂窝地址启发式含 100.64/8、11.x；10/192.168/172.16 视为 WiFi/LAN 类"
        ),
    }


def _filename_start_dt(path: Path) -> datetime | None:
    hint = filename_start_hint(path)
    if not hint:
        return None
    try:
        return datetime.strptime(hint, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _maybe_overlaps_by_name(
    path: Path,
    next_start: datetime | None,
    win_start: datetime | None,
    win_end: datetime | None,
) -> bool:
    """文件名时间粗筛：可能与窗口重叠则返回 True（保守，宁多勿少）。"""
    from datetime import timedelta

    if not (win_start and win_end):
        return True
    start_hint = _filename_start_dt(path)
    if start_hint is None:
        return True  # 无法判断则保留，交给 capinfos
    est_end = next_start if next_start is not None else (start_hint + timedelta(hours=2))
    ov = _overlap_seconds(start_hint, est_end, win_start, win_end)
    return bool(ov and ov > 0)


def probe_networklog_tgame_caps(
    root: Path,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
) -> dict[str, Any]:
    """门禁：是否存在 networklog，且文件名粗筛有与 T_game 重叠的 .cap。

    不调用 Wireshark；仅用于决定是否启动 game_network_cap skill。
    """
    roots = resolve_networklog_roots(root)
    networklog_present = False
    for r in roots:
        name = r.name.lower()
        if name in {"networklog", "netlog"} or (r / "netlog").is_dir() or (r / "NTLog").is_dir():
            networklog_present = True
            break
        if discover_cap_files(r):
            networklog_present = True
            break

    caps: list[Path] = []
    for r in roots:
        caps.extend(discover_cap_files(r))
    uniq: list[Path] = []
    seen: set[str] = set()
    for c in caps:
        key = str(c.resolve())
        if key in seen:
            continue
        seen.add(key)
        uniq.append(c)

    uniq_sorted = sorted(
        uniq,
        key=lambda p: (_filename_start_dt(p) or datetime.min, p.name.lower()),
    )
    starts = [_filename_start_dt(p) for p in uniq_sorted]
    candidates: list[str] = []
    if start and end:
        for i, path in enumerate(uniq_sorted):
            next_start = starts[i + 1] if i + 1 < len(starts) else None
            if _maybe_overlaps_by_name(path, next_start, start, end):
                candidates.append(path.name)
    else:
        candidates = [p.name for p in uniq_sorted]

    should_run = bool(networklog_present and start and end and candidates)
    reason = "ok"
    if not networklog_present:
        reason = "no_networklog"
    elif not (start and end):
        reason = "no_t_game_window"
    elif not uniq_sorted:
        reason = "no_cap_files"
    elif not candidates:
        reason = "no_cap_overlap_t_game"

    return {
        "should_run": should_run,
        "reason": reason,
        "networklog_present": networklog_present,
        "roots": [str(r) for r in roots],
        "cap_count_discovered": len(uniq_sorted),
        "candidate_cap_count": len(candidates),
        "candidate_caps": candidates[:20],
        "window": {
            "start": start.isoformat(sep=" ", timespec="seconds") if start else None,
            "end": end.isoformat(sep=" ", timespec="seconds") if end else None,
        },
    }


def analyze_network_caps(
    root: Path,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    deep: bool = False,
    wireshark_dir: str = "",
    auto_install_wireshark: bool = False,
) -> dict[str, Any]:
    """先筛 T_game 重叠，再仅解析重叠 .cap；--deep 时做协议/会话/双通道判定。"""
    configure_wireshark_cli, resolve_command_path, wireshark_cli_preflight = (
        _import_wireshark_cli()
    )
    configure_wireshark_cli(
        auto_install=auto_install_wireshark, wireshark_dir=wireshark_dir
    )
    ok, msg = wireshark_cli_preflight(
        auto_install=auto_install_wireshark, wireshark_dir=wireshark_dir, quiet=True
    )
    capinfos = resolve_command_path("capinfos")
    tshark = resolve_command_path("tshark")

    roots = resolve_networklog_roots(root)
    caps: list[Path] = []
    for r in roots:
        caps.extend(discover_cap_files(r))
    uniq: list[Path] = []
    seen: set[str] = set()
    for c in caps:
        key = str(c.resolve())
        if key in seen:
            continue
        seen.add(key)
        uniq.append(c)

    # 按文件名时间排序，便于粗筛
    uniq_sorted = sorted(
        uniq,
        key=lambda p: (_filename_start_dt(p) or datetime.min, p.name.lower()),
    )
    starts = [_filename_start_dt(p) for p in uniq_sorted]

    skipped: list[dict[str, Any]] = []
    candidates: list[Path] = []
    for i, path in enumerate(uniq_sorted):
        next_start = starts[i + 1] if i + 1 < len(starts) else None
        if start and end and not _maybe_overlaps_by_name(path, next_start, start, end):
            skipped.append(
                {
                    "path": str(path),
                    "name": path.name,
                    "size_bytes": path.stat().st_size if path.is_file() else 0,
                    "filename_start_hint": filename_start_hint(path),
                    "skip_reason": "filename_time_no_overlap_with_T_game",
                    "parsed": False,
                }
            )
            continue
        candidates.append(path)

    files: list[dict[str, Any]] = []
    overlapping: list[dict[str, Any]] = []
    errors: list[str] = []

    if not capinfos:
        return {
            "status": "blocked",
            "reason": "缺少 capinfos（请安装 Wireshark CLI）",
            "wireshark_preflight": msg,
            "roots": [str(r) for r in roots],
            "cap_count_discovered": len(uniq_sorted),
            "cap_count_parsed": 0,
            "files": [],
            "skipped_non_overlap": skipped,
        }

    # 有时间窗时：默认只解析重叠；无时间窗则解析全部 candidates
    require_window = bool(start and end)
    # 有窗且要求深解析时，deep 默认应对重叠文件开启（由 CLI 传入）
    for path in candidates:
        try:
            info = parse_cap_with_capinfos(path, capinfos=capinfos)
        except subprocess.TimeoutExpired:
            info = {**sniff_pcap_header(path), "error": "capinfos timeout"}
        except Exception as exc:  # noqa: BLE001
            info = {**sniff_pcap_header(path), "error": str(exc)}

        ov = _overlap_seconds(info.get("start_dt"), info.get("end_dt"), start, end)
        info["overlap_with_window_seconds"] = ov
        if require_window:
            info["overlaps_window"] = bool(ov and ov > 0)
        else:
            info["overlaps_window"] = None

        start_dt = info.pop("start_dt", None)
        end_dt = info.pop("end_dt", None)

        # 确认不重叠 → 不深解析，记入 skipped
        if require_window and not info["overlaps_window"]:
            skipped.append(
                {
                    "path": str(path),
                    "name": path.name,
                    "size_bytes": info.get("size_bytes"),
                    "filename_start_hint": info.get("filename_start_hint"),
                    "start_time": info.get("start_time"),
                    "end_time": info.get("end_time"),
                    "packets": info.get("packets"),
                    "skip_reason": "capinfos_no_overlap_with_T_game",
                    "parsed": False,
                }
            )
            continue

        info["parsed"] = True
        if deep and tshark:
            try:
                info["protocol_summary"] = deep_protocol_summary(
                    path, tshark=tshark, start=start, end=end
                )
                info["ip_conversations"] = deep_ip_conversations(
                    path, tshark=tshark, start=start, end=end
                )
                info["interface_traffic"] = deep_interface_traffic(
                    path, tshark=tshark, start=start, end=end
                )
            except subprocess.TimeoutExpired:
                info["deep_error"] = "tshark timeout"
            except Exception as exc:  # noqa: BLE001
                info["deep_error"] = str(exc)
        elif deep and not tshark:
            info["deep_error"] = "缺少 tshark"

        if info.get("error"):
            errors.append(f"{path.name}: {info['error']}")
        files.append(info)
        overlapping.append(
            {
                "path": info.get("path"),
                "overlap_seconds": ov,
                "start_time": info.get("start_time"),
                "end_time": info.get("end_time"),
                "packets": info.get("packets"),
            }
        )
        _ = (start_dt, end_dt)

    dual = judge_dual_channel_from_caps(files) if deep else None

    status = "ok" if files and not all(f.get("error") for f in files) else "partial"
    if require_window and not files and uniq_sorted:
        status = "no_overlap"
    if not uniq_sorted:
        status = "missing"
    if not ok and not capinfos:
        status = "blocked"

    return {
        "status": status,
        "skill": "game_network_cap",
        "input_root": str(Path(root).resolve()),
        "roots_scanned": [str(r) for r in roots],
        "wireshark": {
            "preflight_ok": ok,
            "preflight_message": msg,
            "capinfos": capinfos,
            "tshark": tshark,
        },
        "window": {
            "start": start.isoformat(sep=" ", timespec="seconds") if start else None,
            "end": end.isoformat(sep=" ", timespec="seconds") if end else None,
        },
        "cap_count_discovered": len(uniq_sorted),
        "cap_count_skipped": len(skipped),
        "cap_count_parsed": len(files),
        "overlapping_cap_count": len(overlapping),
        "overlapping_caps": overlapping,
        "skipped_non_overlap": skipped,
        "files": files,
        "dual_channel": dual,
        "errors": errors[:30],
        "notes": [
            "流程：文件名粗筛 → capinfos 确认重叠 → 仅重叠文件解析；非重叠不深解析",
            "--deep：对重叠 cap 跑协议树 / IP 会话 / 接口与本地 IP，并输出 dual_channel",
            "默认跳过 *.cap.tmp* 未完成文件",
        ],
    }
