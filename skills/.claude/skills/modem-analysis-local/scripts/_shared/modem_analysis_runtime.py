from __future__ import annotations

import json
import logging
import os
import re
import sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List, Optional


TRACE_FILES = ("ps.txt", "system.txt", "ota.txt", "sip.txt", "icd.txt", "l1.txt", "l2.txt", "ps_raw.txt")
LINE_TIMESTAMP_RE = re.compile(r"^(?P<stamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d+)?)")
OCCURRENCE_LINE_RE = re.compile(
    r"(?i)(?:time of occurrence|time of issue|occurrence time|发生时间|复现时间|问题时间|时间窗|时间点)[^0-9]{0,24}(?P<time>\d{1,2}:\d{2}(?::\d{2})?)"
)
TIME_TOKEN_RE = re.compile(r"\b(?P<time>\d{1,2}:\d{2}(?::\d{2})?)\b")
STORE_PCELL_RE = re.compile(
    r"(?i)earfcn\[(?P<earfcn>\d+)\].*?pci\[(?P<pci>\d+)\].*?rsrp\[(?P<rsrp>-?\d+(?:\.\d+)?)\].*?"
    r"rsrq\[(?P<rsrq>-?\d+(?:\.\d+)?)\].*?sinr\[(?P<sinr>-?\d+(?:\.\d+)?)\](?:.*?snr\[(?P<snr>-?\d+(?:\.\d+)?)\])?"
)

CRASH_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bassert\b",
        r"fatal error",
        r"err_code",
        r"exception source",
        r"\bphonecrash\b",
        r"\bmodem ee\b",
        r"\bmodem exception\b",
        r"\bsubsystem reset\b",
        r"\bwatchdog\b",
    )
]
SIM_ABNORMAL_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"answertoreset",
        r"\batr\b",
        r"\+esims",
        r"handlesimstatechanged",
        r"tranradioext",
        r"updatesimstate.*(?:absent|unknown|card_io_error|not_ready|locked|rejected|error)",
        r"\bsim[_ -]?io[_ -]?error\b",
        r"\bicc.*(?:absent|error|reject)\b",
        r"\bno sim\b",
        r"\bsim.*(?:absent|unknown|hotplug|removed)\b",
    )
]
SIM_READY_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"updatesimstate.*(?:ready|loaded|present)",
        r"\bsim[_ -]?state.*ready\b",
        r"\bcardstate.*present\b",
        r"\bsim ready\b",
    )
]

CALL_KEYWORDS = [
    "call",
    "voice",
    "volte",
    "vowifi",
    "vonr",
    "ims",
    "sip",
    "invite",
    "paging",
    "atd",
    "ecpi",
    "短信",
    "彩信",
    "补充业务",
    "主叫",
    "被叫",
    "通话",
    "呼叫",
]
DATA_KEYWORDS = [
    "data",
    "attach",
    "apn",
    "bearer",
    "dns",
    "throughput",
    "internet",
    "browse",
    "ip",
    "pdn",
    "esm",
    "emm",
    "上网",
    "数据",
    "断流",
    "无数据",
    "无法注册",
    "lte无法注册",
    "nr无法注册",
    "驻网失败",
    "时延",
]
SIM_ISSUE_KEYWORDS = [
    "esim",
    "atr",
    "icc",
    "不识卡",
    "掉卡",
    "无卡",
    "识卡异常",
    "卡槽",
    "sim io error",
    "sim not",
    "sim absent",
    "sim fail",
    "card io error",
    "card absent",
    "card error",
    "no card",
    "no sim",
    "slot error",
]
SIM_KEYWORDS = [
    "esim",
    "atr",
    "icc",
    "不识卡",
    "掉卡",
    "无卡",
    "识卡异常",
    "卡槽",
    "sim io error",
    "sim absent",
    "card io error",
]
EE_KEYWORDS = [
    "modem ee",
    "modem exception",
    "subsystem reset",
    "watchdog",
    "assert",
    "fatal error",
    "err_code",
    "exception source",
    "crash",
    "死机",
    "重启",
    "异常重启",
    "modem重启",
    "modem死机",
]

CALL_ANALYSIS_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\becpi\b",
        r"\batd\b",
        r"\binvite\b",
        r"\bbye\b",
        r"\b183\b",
        r"\b180\b",
        r"\b200 ok\b",
        r"\b403\b",
        r"\b404\b",
        r"\b408\b",
        r"\b480\b",
        r"\b486\b",
        r"\b487\b",
        r"\b488\b",
        r"\bims\b",
        r"\bvolte\b",
        r"\bvowifi\b",
        r"\bpaging\b",
        r"\bsms\b",
        r"\bsmsc\b",
        r"\bcp[\s_-]?(?:data|ack|error|delivery)\b",
        r"\brp[\s_-]?(?:data|ack|error)\b",
        r"\bsip[\s_-]?message\b",
        r"\bmessage[\s_-]?(?:request|response)\b",
        r"\bsip-frag\b",
        r"\bsms-over-ip\b",
        r"\bsmsc[\s_-]?(?:address|number)\b",
        r"\bclass[\s_-]?2\b",
        r"\bdelivery[\s_-]?(?:report|status)\b",
        r"\bsubmit[\s_-]?(?:report|status)\b",
        r"\bwfc\b",
        r"\bwifi_voice_capa\b",
        r"\bwfc_support\b",
        r"\bsms_capa\b",
        r"\bsms over sgs\b",
    )
]
DATA_ANALYSIS_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\battach\b",
        r"\bapn\b",
        r"\bbearer\b",
        r"\bdns\b",
        r"\bip\b",
        r"\bpdn\b",
        r"\besm\b",
        r"\bemm\b",
        r"\bthroughput\b",
        r"\bdeactivate\b",
        r"\breject\b",
        r"断流",
        r"无数据",
    )
]
SIM_ANALYSIS_PATTERNS = SIM_ABNORMAL_PATTERNS + [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bicc\b",
        r"\bsim\b",
        r"\bcard io error\b",
        r"\babsent\b",
        r"\bunknown\b",
    )
]

CALIBRATION_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"calibration",
        r"cal data",
        r"cal loss",
        r"cal fail",
        r"cal missing",
        r"cal invalid",
        r"rf cal",
        r"antenna cal",
    )
]

CALIBRATION_RAT_RE = re.compile(
    r"(?i)(?:LTE|NR|WCDMA|GSM|TDSCDMA|CDMA2000|5G|4G|3G|2G)",
)

EE_ANALYSIS_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bmodem ee\b",
        r"\bmodem exception\b",
        r"\bsubsystem reset\b",
        r"\bwatchdog\b",
        r"\bassert\b",
        r"\bfatal error\b",
        r"\berr_code\b",
        r"\bexception source\b",
        r"\bmd_state\b",
        r"\bmdboot\b",
        r"\bmd_off\b",
        r"\bmd_on\b",
        r"\bexcp\b",
        r"\bcrash\b",
    )
]


DEFAULT_MANIFEST = {
    "issue_key": "",
    "workspace_root": "",
    "final_log_root": "",
    "jira": {
        "summary": "",
        "description": "",
        "comments_text": "",
        "box_urls": [],
        "url_roles": {},
    },
    "downloads": {
        "download_root": "",
        "download_dirs": [],
        "results": [],
    },
    "extraction": {
        "output_root": "",
        "extracted_dirs": [],
        "normalized_log_roots": [],
        "results": [],
        "filter_results": [],
    },
    "trace_exports": {
        "groups": [],
        "results": [],
        "aggregated_files": {},
        "copied_support_files": {},
    },
    "analysis": {
        "analysis_type": "",
        "evidence": [],
        "timeline": [],
        "candidate_causes": [],
        "l0_baseline": {},
        "l1_business": {
            "primary_domain": "",
            "secondary_domains": [],
            "routing_reason": [],
            "excluded_domains": [],
            "status": "pending",
        },
        "l2_domains": {
            "call": {},
            "data": {},
            "sim": {},
            "ee": {},
        },
        "l3_conclusion": {},
        "final_report": "",
    },
    "db_cache": {
        "status": "",
        "source": "",
        "checker": {},
        "writer": {},
        "write_status": "",
    },
    "publish": {
        "jira_comment_posted": False,
        "comment_timestamp": "",
        "comment_preview": "",
    },
}


def configure_stdio() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass


def setup_skill_logger(manifest_path: str, issue_key: str) -> logging.Logger:
    """创建 skill 执行日志，写入 manifest 同级目录 {issue_key}-skill.log（追加模式）。

    多个 run_*.py 脚本共用同一个日志文件，通过 logger name 区分来源。
    finalize_analysis.py 最终负责将该文件上传至 NAS 并删除本地副本。
    """
    logger_name = f"modem_skill.{issue_key}"
    logger = logging.getLogger(logger_name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    fmt = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(name)s - %(message)s",
        datefmt="%H:%M:%S",
    )

    ch = logging.StreamHandler(sys.stderr)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    log_path = Path(manifest_path).parent / f"{issue_key}-skill.log"
    fh = logging.FileHandler(str(log_path), encoding="utf-8", mode="a")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logger


def merge_defaults(target: Dict[str, Any], defaults: Dict[str, Any]) -> Dict[str, Any]:
    for key, value in defaults.items():
        if key not in target:
            target[key] = deepcopy(value)
        elif isinstance(value, dict) and isinstance(target.get(key), dict):
            merge_defaults(target[key], value)
    return target


def load_manifest(path: Optional[str]) -> Dict[str, Any]:
    if not path or not os.path.exists(path):
        return deepcopy(DEFAULT_MANIFEST)
    with open(path, "r", encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("manifest 格式错误")
    return merge_defaults(payload, deepcopy(DEFAULT_MANIFEST))


def save_manifest(path: str, manifest: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    merge_defaults(manifest, deepcopy(DEFAULT_MANIFEST))
    manifest["_meta"] = {"updated_at": datetime.now().isoformat(timespec="seconds")}
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def round_float(value: Optional[float], digits: int = 2) -> Optional[float]:
    if value is None:
        return None
    return round(float(value), digits)


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def trim_text(text: str, limit: int = 240) -> str:
    text = normalize_space(text)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def parse_line_timestamp(line: str) -> Optional[datetime]:
    match = LINE_TIMESTAMP_RE.match(line or "")
    if not match:
        return None
    stamp = match.group("stamp")
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(stamp, fmt)
        except ValueError:
            continue
    return None


def parse_hms(text: str) -> Optional[int]:
    parts = text.split(":")
    if len(parts) not in (2, 3):
        return None
    try:
        hour = int(parts[0])
        minute = int(parts[1])
        second = int(parts[2]) if len(parts) == 3 else 0
    except ValueError:
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59):
        return None
    return hour * 3600 + minute * 60 + second


def seconds_of_day(moment: datetime) -> int:
    return moment.hour * 3600 + moment.minute * 60 + moment.second


def parse_occurrence_times(manifest: Dict[str, Any]) -> List[int]:
    texts = [
        manifest.get("jira", {}).get("summary", ""),
        manifest.get("jira", {}).get("description", ""),
        manifest.get("jira", {}).get("comments_text", ""),
    ]
    values: List[int] = []
    for text in texts:
        for line in (text or "").splitlines():
            match = OCCURRENCE_LINE_RE.search(line)
            if not match:
                continue
            seconds = parse_hms(match.group("time"))
            if seconds is not None and seconds not in values:
                values.append(seconds)
    if values:
        return values
    for text in texts:
        for match in TIME_TOKEN_RE.finditer(text or ""):
            seconds = parse_hms(match.group("time"))
            if seconds is not None and seconds not in values:
                values.append(seconds)
            if len(values) >= 3:
                return values
    return values


def resolve_log_root(manifest: Dict[str, Any], manifest_path: Optional[str] = None) -> str:
    """根据 manifest 与 manifest 路径解析最终日志根目录的绝对路径。

    遵循 Phase 1→Phase 2 契约：
    - manifest.final_log_root 通常为相对路径（如 "."）
    - 基于 manifest 文件所在目录解析
    - 兜底：manifest 所在目录本身即 workspace 根
    """
    final_log_root = (manifest.get("final_log_root") or "").strip()
    manifest_dir = os.path.abspath(os.path.dirname(manifest_path)) if manifest_path else ""

    if final_log_root and os.path.isabs(final_log_root):
        return os.path.abspath(final_log_root)
    if final_log_root and manifest_dir:
        return os.path.abspath(os.path.join(manifest_dir, final_log_root))
    if manifest_dir:
        return manifest_dir
    if final_log_root:
        return os.path.abspath(final_log_root)
    raise FileNotFoundError("无法解析 final_log_root：manifest 与 manifest_path 都未提供有效根目录。")


def discover_log_groups(final_log_root: str) -> List[Dict[str, Any]]:
    root = os.path.abspath(final_log_root)
    if not os.path.isdir(root):
        raise FileNotFoundError("无效的 final_log_root: %s" % root)

    groups: List[Dict[str, Any]] = []

    def build_group(name: str, path: str) -> Optional[Dict[str, Any]]:
        files: Dict[str, str] = {}
        for filename in TRACE_FILES:
            candidate = os.path.join(path, filename)
            if os.path.isfile(candidate):
                files[filename[:-4]] = os.path.abspath(candidate)
        if not files:
            return None
        return {"name": name, "path": os.path.abspath(path), "files": files}

    root_group = build_group(os.path.basename(root) or "root", root)
    if root_group:
        groups.append(root_group)

    for entry in sorted(os.listdir(root)):
        path = os.path.join(root, entry)
        if not os.path.isdir(path):
            continue
        group = build_group(entry, path)
        if group:
            groups.append(group)
    return groups


def select_primary_group(groups: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not groups:
        raise ValueError("没有可用的日志分组")

    def rank(group: Dict[str, Any]) -> tuple:
        name = (group.get("name") or "").lower()
        if "dut" in name:
            return (0, name)
        if name in {"root", "final_logs"}:
            return (1, name)
        if "ref" in name:
            return (3, name)
        return (2, name)

    return sorted(groups, key=rank)[0]


def read_text_lines(path: Optional[str]) -> List[str]:
    if not path or not os.path.isfile(path):
        return []
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        return handle.readlines()


def load_group_lines(group: Dict[str, Any]) -> Dict[str, List[str]]:
    return {name: read_text_lines(path) for name, path in (group.get("files") or {}).items()}


def build_issue_text(manifest: Dict[str, Any]) -> str:
    jira = manifest.get("jira", {})
    return "\n".join(
        value
        for value in (
            jira.get("summary", ""),
            jira.get("description", ""),
            jira.get("comments_text", ""),
        )
        if value
    )


def text_has_any_keyword(text: str, keywords: Iterable[str]) -> bool:
    lowered = (text or "").lower()
    return any(keyword.lower() in lowered for keyword in keywords)


def filter_lines_by_occurrence(
    lines: List[str], occurrence_times: List[int], tolerance_seconds: int = 180
) -> List[str]:
    if not occurrence_times:
        return lines
    filtered: List[str] = []
    for line in lines:
        stamp = parse_line_timestamp(line)
        if not stamp:
            continue
        current = seconds_of_day(stamp)
        if any(abs(current - occurrence) <= tolerance_seconds for occurrence in occurrence_times):
            filtered.append(line)
    return filtered or lines


def evidence_item(file_key: str, line: str) -> Dict[str, Any]:
    stamp = parse_line_timestamp(line)
    return {
        "file": file_key,
        "timestamp": stamp.isoformat(timespec="seconds") if stamp else "",
        "text": trim_text(line),
    }


def find_pattern_matches(
    lines_by_file: Dict[str, List[str]],
    patterns: Iterable[re.Pattern[str]],
    occurrence_times: List[int],
    limit: int = 12,
) -> List[Dict[str, Any]]:
    matches: List[Dict[str, Any]] = []
    for file_key, lines in lines_by_file.items():
        source_lines = filter_lines_by_occurrence(lines, occurrence_times, tolerance_seconds=240)
        for line in source_lines:
            if any(pattern.search(line) for pattern in patterns):
                matches.append(evidence_item(file_key, line))
                if len(matches) >= limit:
                    return matches
    if matches or not occurrence_times:
        return matches
    for file_key, lines in lines_by_file.items():
        for line in lines:
            if any(pattern.search(line) for pattern in patterns):
                matches.append(evidence_item(file_key, line))
                if len(matches) >= limit:
                    return matches
    return matches


def linear_score(value: Optional[float], minimum: float, maximum: float) -> Optional[float]:
    if value is None:
        return None
    if value <= minimum:
        return 0.0
    if value >= maximum:
        return 10.0
    return ((value - minimum) / (maximum - minimum)) * 10.0


def weighted_average(items: Iterable[Dict[str, Any]]) -> Optional[float]:
    weighted_sum = 0.0
    total_weight = 0.0
    for item in items:
        value = item.get("value")
        weight = item.get("weight")
        if value is None or weight is None:
            continue
        weighted_sum += float(value) * float(weight)
        total_weight += float(weight)
    if total_weight <= 0:
        return None
    return weighted_sum / total_weight


def scale_store_value(raw_value: Optional[str]) -> Optional[float]:
    if raw_value is None:
        return None
    return float(raw_value) / 4.0


def extract_store_pcell_samples(lines: List[str], occurrence_times: List[int]) -> List[Dict[str, Any]]:
    samples: List[Dict[str, Any]] = []
    for line in filter_lines_by_occurrence(lines, occurrence_times, tolerance_seconds=240):
        if "[MRM] store PCell" not in line or "rsrp[" not in line:
            continue
        match = STORE_PCELL_RE.search(line)
        if not match:
            continue
        stamp = parse_line_timestamp(line)
        if not stamp:
            continue
        rsrp = scale_store_value(match.group("rsrp"))
        rsrq = scale_store_value(match.group("rsrq"))
        sinr = scale_store_value(match.group("sinr"))
        snr = scale_store_value(match.group("snr")) if match.group("snr") is not None else sinr
        strength_score = linear_score(rsrp, -120.0, -95.0)
        quality_score = linear_score(rsrq, -20.0, -12.0)
        snr_score = linear_score(snr, -5.0, 5.0)
        call_score = weighted_average(
            [
                {"value": strength_score, "weight": 0.4},
                {"value": quality_score, "weight": 0.6},
            ]
        )
        generic_score = weighted_average(
            [
                {"value": strength_score, "weight": 0.6},
                {"value": quality_score, "weight": 0.4},
            ]
        )
        indicator_score = weighted_average(
            [
                {"value": strength_score, "weight": 0.45},
                {"value": quality_score, "weight": 0.35},
                {"value": snr_score, "weight": 0.20},
            ]
        )
        samples.append(
            {
                "timestamp": stamp,
                "rat": "4G",
                "earfcn": match.group("earfcn"),
                "pci": match.group("pci"),
                "rsrp": rsrp,
                "rsrq": rsrq,
                "sinr": sinr,
                "snr": snr,
                "strength_score": round_float(strength_score),
                "quality_score": round_float(quality_score),
                "call_score": round_float(call_score),
                "generic_score": round_float(generic_score),
                "indicator_score": round_float(indicator_score),
                "line": trim_text(line),
            }
        )
    return samples


def analyze_subsystem_state(lines_by_file: Dict[str, List[str]], occurrence_times: List[int]) -> Dict[str, Any]:
    """分析ModemState：只要有EE都要流转到l2-ee"""
    matches = find_pattern_matches(lines_by_file, CRASH_PATTERNS, occurrence_times, limit=8)
    return {
        "status": "abnormal" if matches else "normal",
        "evidence": matches,
        "route_to_ee": len(matches) > 0,
    }


def analyze_calibration_state(lines_by_file: Dict[str, List[str]], occurrence_times: List[int]) -> Dict[str, Any]:
    """分析射频校准参数：记录丢失的校准参数，识别是哪些RAT的参数丢失"""
    cal_matches = find_pattern_matches(lines_by_file, CALIBRATION_PATTERNS, occurrence_times, limit=20)
    
    missing_rats = set()
    cal_details = []
    for item in cal_matches:
        text = item.get("text", "")
        rat_matches = CALIBRATION_RAT_RE.findall(text)
        for rat in rat_matches:
            missing_rats.add(rat.upper())
        cal_details.append({
            "timestamp": item.get("timestamp", ""),
            "file": item.get("file", ""),
            "text": text,
            "rats": list(set(rat_matches)),
        })
    
    return {
        "status": "abnormal" if cal_matches else "normal",
        "missing_rats": list(missing_rats),
        "evidence": cal_matches,
        "details": cal_details,
    }


def analyze_sim_state(
    issue_text: str,
    lines_by_file: Dict[str, List[str]],
    occurrence_times: List[int],
) -> Dict[str, Any]:
    """分析SIMState：热插拔、开关飞行模型，记录时间点"""
    abnormal = find_pattern_matches(lines_by_file, SIM_ABNORMAL_PATTERNS, occurrence_times, limit=8)
    ready = find_pattern_matches(lines_by_file, SIM_READY_PATTERNS, occurrence_times, limit=4)
    status = "abnormal" if abnormal else ("ready" if ready else "unknown")
    issue_is_sim = text_has_any_keyword(issue_text, SIM_ISSUE_KEYWORDS)
    alignment = "n/a"
    if issue_is_sim and abnormal:
        alignment = "confirmed"
    elif issue_is_sim and not abnormal:
        alignment = "missing"
    
    hotplug_events = []
    airplane_mode_events = []
    
    for file_key, lines in lines_by_file.items():
        for line in filter_lines_by_occurrence(lines, occurrence_times, tolerance_seconds=240):
            esims_match = re.search(r'\+ESIMS:\s*(\d+)', line)
            if esims_match:
                value = esims_match.group(1)
                event_type = "SIM_PLUG_OUT" if value == "11" else ("SIM_PLUG_IN" if value == "12" else f"UNKNOWN({value})")
                stamp = parse_line_timestamp(line)
                hotplug_events.append({
                    "timestamp": stamp.isoformat(timespec="seconds") if stamp else "",
                    "file": file_key,
                    "event": event_type,
                    "value": value,
                    "text": trim_text(line),
                })
            
            airplane_match = re.search(r'hasAirplaneModeOnlChanged\s*=\s*(TRUE|FALSE)', line, re.IGNORECASE)
            if airplane_match:
                value = airplane_match.group(1).upper()
                stamp = parse_line_timestamp(line)
                airplane_mode_events.append({
                    "timestamp": stamp.isoformat(timespec="seconds") if stamp else "",
                    "file": file_key,
                    "value": value,
                    "text": trim_text(line),
                })
    
    return {
        "status": status,
        "evidence": abnormal or ready,
        "abnormal_evidence": abnormal,
        "ready_evidence": ready,
        "issue_alignment": alignment,
        "hotplug_events": hotplug_events,
        "airplane_mode_events": airplane_mode_events,
    }


def summarize_samples(samples: List[Dict[str, Any]]) -> List[str]:
    if not samples:
        return ["时间窗内未提取到 store PCell 信号样本。"]
    latest = samples[-1]
    generic_scores = [sample["generic_score"] for sample in samples if sample.get("generic_score") is not None]
    indicator_scores = [sample["indicator_score"] for sample in samples if sample.get("indicator_score") is not None]
    return [
        "主分析分组: %s" % latest.get("rat", "unknown"),
        "关键小区: earfcn=%s pci=%s" % (latest.get("earfcn") or "?", latest.get("pci") or "?"),
        "采样数量: %s" % len(samples),
        "最近一次信号: RSRP=%s dBm, RSRQ=%s dB, SINR=%s dB"
        % (latest.get("rsrp"), latest.get("rsrq"), latest.get("sinr")),
        "平均 generic score=%s, average indicator score=%s"
        % (
            round_float(mean(generic_scores) if generic_scores else None),
            round_float(mean(indicator_scores) if indicator_scores else None),
        ),
    ]


def build_l0_result(manifest: Dict[str, Any], log_root: Optional[str] = None) -> Dict[str, Any]:
    final_log_root = os.path.abspath(log_root or manifest.get("final_log_root") or "")
    if not final_log_root:
        raise ValueError("缺少 final_log_root")

    groups = discover_log_groups(final_log_root)
    primary_group = select_primary_group(groups)
    lines_by_file = load_group_lines(primary_group)
    occurrence_times = parse_occurrence_times(manifest)
    issue_text = build_issue_text(manifest)
    issue_is_sim = text_has_any_keyword(issue_text, SIM_ISSUE_KEYWORDS)

    samples = extract_store_pcell_samples(lines_by_file.get("ps", []), occurrence_times)

    subsystem_state = analyze_subsystem_state(lines_by_file, occurrence_times)
    calibration_state = analyze_calibration_state(lines_by_file, occurrence_times)
    sim_state = analyze_sim_state(issue_text, lines_by_file, occurrence_times)

    reasons: List[str] = []
    triggered_rules: List[str] = []
    should_continue = True
    is_modemee_issue = False

    if subsystem_state["status"] == "abnormal":
        ee_evidence_texts = [item.get("text", "").lower() for item in subsystem_state.get("evidence", [])]
        has_modemee_keyword = any(
            keyword in " ".join(ee_evidence_texts)
            for keyword in ("modem ee", "modem exception", "assert", "fatal error", "watchdog")
        )
        issue_text_lower = issue_text.lower()
        has_modemee_in_issue = any(
            keyword in issue_text_lower
            for keyword in ("modem ee", "modem exception", "aee", "exception", "ee)", "crash", "死机", "重启")
        )
        
        if has_modemee_keyword or has_modemee_in_issue:
            is_modemee_issue = True
            triggered_rules.append("modemee_detected")
            reasons.append("检测到 ModemEE / Assert，将路由到 ee 域进行深度分析。")
            should_continue = True
        else:
            should_continue = False
            triggered_rules.append("subsystem_crash")
            reasons.append("时间窗内存在 ModemEE / Assert / Fatal error 等基础环境异常。")

    if issue_is_sim:
        if sim_state["issue_alignment"] == "missing":
            should_continue = False
            triggered_rules.append("sim_issue_without_evidence")
            reasons.append("Jira 主诉为 SIM/识卡类问题，但时间窗内未找到图二要求的关键 SIM 异常证据。")
    elif sim_state["status"] == "abnormal":
        should_continue = False
        triggered_rules.append("sim_not_ready")
        reasons.append("时间窗内 SIM 状态异常，基础环境不满足继续做业务链路分析。")

    gate_status = "valid" if should_continue else "invalid"
    validity_gate = {
        "status": gate_status,
        "decision": gate_status,
        "is_valid_problem": should_continue,
        "should_continue": should_continue,
        "is_modemee_issue": is_modemee_issue,
        "triggered_rules": triggered_rules,
        "reasons": reasons,
        "occurrence_times": occurrence_times,
        "primary_group": {
            "name": primary_group.get("name", ""),
            "path": primary_group.get("path", ""),
        },
    }

    result = {
        "modem_state": subsystem_state,
        "calibration_state": calibration_state,
        "sim_state": sim_state,
        "validity_gate": validity_gate,
        "should_continue": should_continue,
        "summary": summarize_samples(samples) + reasons,
        "gaps": [
            gap
            for gap in (
                "未在时间窗内发现明确 SIM ready 证据。" if sim_state["status"] == "unknown" else "",
                "未在时间窗内发现 store PCell 样本。" if not samples else "",
            )
            if gap
        ],
    }
    return result


def route_business_domain(manifest: Dict[str, Any]) -> Dict[str, Any]:
    """L1 业务域路由：ModemEE 优先判断，然后再区分 call/data/sim"""
    l0 = manifest.get("analysis", {}).get("l0_baseline", {})
    gate = l0.get("validity_gate", {})
    gate_status = gate.get("status") or gate.get("decision")
    if gate_status == "invalid" or l0.get("should_continue") is False:
        return {
            "primary_domain": "other",
            "secondary_domains": [],
            "routing_reason": ["L0 已判定为无效问题，L1 不再继续业务域路由。"],
            "excluded_domains": ["call", "data", "sim", "ee"],
            "status": "skipped_invalid",
        }

    # ===== 第一步：优先判断 ModemEE =====
    modem_state = l0.get("modem_state", {}) or l0.get("subsystem_state", {})
    is_modemee_issue = gate.get("is_modemee_issue", False)
    
    # 如果 L0 识别了 ModemEE（log 和 JIRA 描述），优先路由到 l2-ee
    if is_modemee_issue or modem_state.get("route_to_ee"):
        return {
            "primary_domain": "ee",
            "secondary_domains": [],
            "routing_reason": [
                "L0 已识别 ModemEE 问题（modem_state.route_toee=true 或 is_modemee_issue=true），优先路由到 l2-ee 进行深度分析。"
            ],
            "excluded_domains": ["call", "data", "sim"],
            "status": "done",
            "routing_priority": "ee_first",
        }

    # ===== 第二步：如果不是 ModemEE，再区分 call、data、sim =====
    issue_text = build_issue_text(manifest)
    lowered = issue_text.lower()
    scores = {
        "call": sum(1 for keyword in CALL_KEYWORDS if keyword.lower() in lowered),
        "data": sum(1 for keyword in DATA_KEYWORDS if keyword.lower() in lowered),
        "sim": sum(1 for keyword in SIM_KEYWORDS if keyword.lower() in lowered),
        "ee": sum(1 for keyword in EE_KEYWORDS if keyword.lower() in lowered),
    }
    sim_state = l0.get("sim_state", {})
    if sim_state.get("status") == "abnormal":
        scores["sim"] += 4
    if any("ims" in item.get("text", "").lower() for item in sim_state.get("evidence", [])):
        scores["call"] += 1

    modem_state = l0.get("modem_state", {})
    if modem_state.get("status") == "abnormal":
        scores["ee"] += 6
        for item in modem_state.get("evidence", []):
            text = item.get("text", "").lower()
            if "modem ee" in text or "modem exception" in text or "phonecrash" in text:
                scores["ee"] += 3
                break

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    primary_domain = ranked[0][0] if ranked and ranked[0][1] > 0 else "other"
    secondary = [name for name, score in ranked[1:] if score > 0]
    reasons = ["%s score=%s" % (name, score) for name, score in ranked if score > 0]
    if not reasons:
        reasons = ["Jira 文本与 L0 指标均未给出稳定的单主域信号。"]
    excluded = [name for name, score in ranked if name != primary_domain and score == 0]

    return {
        "primary_domain": primary_domain,
        "secondary_domains": secondary,
        "routing_reason": reasons,
        "excluded_domains": excluded,
        "status": "done",
        "routing_priority": "normal",
    }


def _domain_match_lines(
    lines_by_file: Dict[str, List[str]],
    patterns: Iterable[re.Pattern[str]],
    occurrence_times: List[int],
    limit: int = 16,
) -> List[Dict[str, Any]]:
    matches = find_pattern_matches(lines_by_file, patterns, occurrence_times, limit=limit)
    return sorted(matches, key=lambda item: (item.get("timestamp", ""), item.get("file", "")))


def _candidate_causes_for_domain(domain: str, matches: List[Dict[str, Any]], l0: Dict[str, Any]) -> List[str]:
    texts = [item.get("text", "").lower() for item in matches]
    causes: List[str] = []
    if domain == "call":
        if any(token in text for text in texts for token in ("403", "404", "408", "480", "486", "487", "488")):
            causes.append("SIP/呼叫流程中出现拒绝码或失败响应。")
        if any("ims" in text and ("fail" in text or "oos" in text or "not registered" in text) for text in texts):
            causes.append("IMS 注册或驻网条件异常，影响语音相关业务。")
        if any("wifi_voice_capa:0/0" in text for text in texts):
            causes.append("设备不支持 WiFi 语音功能，无法使用 VoWiFi 短信。")
        if any("wfc_support:0/1" in text for text in texts):
            causes.append("WFC 支持初始为 0，需检查 WiFi 通话开关配置。")
        if any("sms over sgs is preferred" in text for text in texts):
            causes.append("运营商配置优先使用 SGs 而非 IMS 短信，影响 VoWiFi 短信功能。")
        if any("sms" in text and ("fail" in text or "error" in text or "reject" in text) for text in texts):
            causes.append("SMS 发送失败，需检查短信流程。")
        if any("cp-error" in text or "rp-error" in text for text in texts):
            causes.append("SMS CP/RP 层传输失败，需检查网络侧配置。")
        if any("sip-message" in text or "sip message" in text for text in texts) and any(token in text for text in texts for token in ("403", "404", "500", "503")):
            causes.append("SMS over VoWiFi 被 SIP 层拒绝。")
        if any("sms-over-ip" in text or "sms over ip" in text for text in texts) and not any("200 ok" in text for text in texts):
            causes.append("SMS over IP 流程未完成，需检查 IMS 注册状态。")
        if not causes and not matches:
            causes.append("日志中未定位到稳定的 call 关键流程，需先确认问题时间窗或业务域。")
    elif domain == "data":
        if any(token in text for text in texts for token in ("reject", "deactivate", "dns", "apn", "pdn", "esm")):
            causes.append("数据侧 attach / bearer / DNS / APN 流程中存在失败或拒绝。")
        if not causes and not matches:
            causes.append("日志中未定位到稳定的数据业务流程，需先确认问题时间窗或业务域。")
    elif domain == "sim":
        if any("answertoreset" in text or "atr" in text for text in texts):
            causes.append("SIM 接触或 ATR 解析异常。")
        if any("+esims" in text or "handlesimstatechanged" in text for text in texts):
            causes.append("eSIM / Telephony 状态切换链路异常。")
        if any("updatesimstate" in text for text in texts):
            causes.append("SIM 状态机上报异常。")
        if l0.get("modem_state", {}).get("status") == "abnormal":
            causes.append("ModemEE 干扰了 SIM 结论，需要先恢复基础环境。")
        if not causes and not matches:
            causes.append("未找到足够的 SIM 关键证据，建议先核对时间窗和 DUT 分组。")
    elif domain == "ee":
        if any("modem ee" in text or "modem exception" in text for text in texts):
            causes.append("检测到 Modem Exception / Modem EE，需要进一步分析异常类型和触发原因。")
        if any("phonecrash" in text for text in texts):
            causes.append("检测到 PhoneCrash，需要确认是否与 Modem 相关。")
        if any("subsystem reset" in text or "watchdog" in text for text in texts):
            causes.append("检测到子系统复位或看门狗触发。")
        if any("assert" in text or "fatal error" in text for text in texts):
            causes.append("检测到断言失败或致命错误。")
        if not causes and not matches:
            causes.append("未找到足够的 ModemEE 关键证据，建议先核对时间窗和日志完整性。")
    return causes[:4]


def analyze_domain(manifest: Dict[str, Any], domain: str, log_root: Optional[str] = None) -> Dict[str, Any]:
    l0 = manifest.get("analysis", {}).get("l0_baseline", {})
    gate = l0.get("validity_gate", {})
    gate_status = gate.get("status") or gate.get("decision")
    if gate_status == "invalid" or l0.get("should_continue") is False:
        return {
            "status": "skipped_invalid",
            "timeline": [],
            "evidence": [],
            "candidate_causes": [],
            "gaps": ["L0 已判定为无效问题，当前域分析被短路。"],
        }

    final_log_root = os.path.abspath(log_root or manifest.get("final_log_root") or "")
    groups = discover_log_groups(final_log_root)
    primary_group = select_primary_group(groups)
    lines_by_file = load_group_lines(primary_group)
    occurrence_times = parse_occurrence_times(manifest)

    if domain == "call":
        patterns = CALL_ANALYSIS_PATTERNS
    elif domain == "data":
        patterns = DATA_ANALYSIS_PATTERNS
    elif domain == "sim":
        patterns = SIM_ANALYSIS_PATTERNS
    elif domain == "ee":
        patterns = EE_ANALYSIS_PATTERNS
    else:
        raise ValueError("unsupported domain: %s" % domain)

    matches = _domain_match_lines(lines_by_file, patterns, occurrence_times, limit=50)
    candidate_causes = _candidate_causes_for_domain(domain, matches, l0)
    return {
        "status": "done" if matches else "insufficient_evidence",
        "timeline": matches[:12],
        "evidence": matches[:20],
        "candidate_causes": candidate_causes,
        "gaps": [] if matches else ["未在当前时间窗找到足够的 %s 关键日志。" % domain],
    }


def compatibility_analysis_type(primary_domain: str) -> str:
    if primary_domain in {"call", "data", "ee"}:
        return primary_domain
    return "other"


def build_l3_result(manifest: Dict[str, Any]) -> Dict[str, Any]:
    analysis = manifest.get("analysis", {})
    l0 = analysis.get("l0_baseline", {})
    gate = l0.get("validity_gate", {})
    l1 = analysis.get("l1_business", {})
    l2_domains = analysis.get("l2_domains", {})

    gate_status = gate.get("status") or gate.get("decision")
    if gate_status == "invalid" or l0.get("should_continue") is False:
        reasons = gate.get("reasons") or ["基础环境不满足继续分析。"]
        next_actions = [
            "先处理基础环境问题，再重新抓取同时间窗日志复现。",
            "优先确认 SIM 状态和子系统稳定性是否满足复测条件。",
        ]
        report = "\n".join(
            [
                "结论: 当前问题判定为无效问题。",
                "原因:",
                *["- %s" % reason for reason in reasons],
                "建议:",
                *["- %s" % action for action in next_actions],
            ]
        )
        return {
            "l3_conclusion": {
                "primary_root_cause": "无效问题：基础环境不满足继续分析。",
                "secondary_factors": reasons[1:],
                "next_actions": next_actions,
                "confidence": "high" if len(reasons) >= 2 else "medium",
            },
            "final_report": report,
            "compat_evidence": l0.get("modem_state", {}).get("evidence", []),
            "compat_timeline": [],
            "compat_causes": reasons,
        }

    primary_domain = l1.get("primary_domain") or "other"
    domain_payload = l2_domains.get(primary_domain, {}) if primary_domain in l2_domains else {}
    candidate_causes = list(domain_payload.get("candidate_causes") or [])
    modem_state = l0.get("modem_state", {})
    if modem_state.get("status") == "abnormal":
        candidate_causes.append("子系统存在异常，会降低结论可信度。")
    candidate_causes = list(dict.fromkeys(candidate_causes))

    primary_cause = candidate_causes[0] if candidate_causes else "当前证据不足，未能稳定定位单一根因。"
    next_actions = [
        "结合时间窗继续补抓更完整的 %s 业务日志。" % primary_domain,
        "若问题可稳定复现，补充 DUT/REF 对比和更精确的发生时间点。",
    ]
    report_lines = [
        "结论: %s" % primary_cause,
        "主业务域: %s" % primary_domain,
    ]
    if candidate_causes:
        report_lines.append("关键判断:")
        report_lines.extend("- %s" % cause for cause in candidate_causes[:4])
    evidence = domain_payload.get("evidence") or []
    if evidence:
        report_lines.append("关键证据:")
        report_lines.extend("- [%s] %s" % (item.get("file", "?"), item.get("text", "")) for item in evidence[:5])
    report_lines.append("建议:")
    report_lines.extend("- %s" % action for action in next_actions)

    return {
        "l3_conclusion": {
            "primary_root_cause": primary_cause,
            "secondary_factors": candidate_causes[1:4],
            "next_actions": next_actions,
            "confidence": "medium" if candidate_causes else "low",
        },
        "final_report": "\n".join(report_lines),
        "compat_evidence": evidence,
        "compat_timeline": domain_payload.get("timeline") or [],
        "compat_causes": candidate_causes,
    }


def apply_l0_result(manifest: Dict[str, Any], result: Dict[str, Any], log_root: Optional[str] = None) -> Dict[str, Any]:
    # 不再强写绝对路径到 manifest——遵循 Phase 1→Phase 2 契约：final_log_root 保持相对路径。
    # 如果调用方显式传了 log_root，仅在 manifest 中无值时回填。
    if log_root and not manifest.get("final_log_root"):
        manifest["final_log_root"] = log_root
    manifest["analysis"]["l0_baseline"] = result
    return manifest


def apply_l1_result(manifest: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    manifest["analysis"]["l1_business"] = result
    manifest["analysis"]["analysis_type"] = compatibility_analysis_type(result.get("primary_domain") or "other")
    return manifest


def apply_l2_result(manifest: Dict[str, Any], domain: str, result: Dict[str, Any]) -> Dict[str, Any]:
    manifest["analysis"]["l2_domains"][domain] = result
    return manifest


def apply_l3_result(manifest: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    manifest["analysis"]["l3_conclusion"] = result["l3_conclusion"]
    manifest["analysis"]["final_report"] = result["final_report"]
    manifest["analysis"]["evidence"] = result.get("compat_evidence") or []
    manifest["analysis"]["timeline"] = result.get("compat_timeline") or []
    manifest["analysis"]["candidate_causes"] = result.get("compat_causes") or []
    return manifest
