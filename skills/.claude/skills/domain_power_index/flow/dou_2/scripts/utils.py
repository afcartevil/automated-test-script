"""
工具函数模块。工作区根解析见 analysis/base/lib/repo_paths.py。
"""
import os
import re
import json
import pandas as pd
from datetime import datetime
from pathlib import Path
import hashlib
import pickle

from paths import CPU_CACHE_DIR


def setup_windows_encoding():
    """修复Windows中文编码问题"""
    import sys
    if sys.platform == "win32":
        os.environ["PYTHONIOENCODING"] = "utf-8"
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
            sys.stderr.reconfigure(encoding='utf-8')


def _is_excluded_report_xlsx(filename):
    """排除对比产物、临时文件等非数据源 xlsx。"""
    lower = filename.lower()
    if not lower.endswith(".xlsx") or lower.startswith("~$"):
        return True
    for token in ("dou3.0", "版本数据对比", "对比结果", "topn_", "scene_compare"):
        if token in lower:
            return True
    return False


def _xlsx_has_report_sheet(file_path):
    """DOU 场景对比至少需要 report 工作表。"""
    try:
        xl = pd.ExcelFile(file_path)
        return any(str(s).strip().lower() == "report" for s in xl.sheet_names)
    except Exception:
        return False


def _score_report_xlsx(file_path):
    """为候选 xlsx 打分，分数越高越优先。"""
    filename = os.path.basename(file_path).lower()
    parent = os.path.basename(os.path.dirname(file_path)).lower()
    score = 0
    if _xlsx_has_report_sheet(file_path):
        score += 100
    else:
        return -1
    if parent == "meta_report":
        score += 50
    if filename == "testreport.xlsx":
        score += 40
    elif "testreport" in filename or "test_report" in filename:
        score += 30
    elif "report" in filename:
        score += 20
    elif "dou" in filename or "meta" in filename:
        score += 10
    return score


def _iter_folder_xlsx(folder_path):
    """遍历目录下候选 xlsx（浅层优先：meta_report 先于全目录 walk）。"""
    meta_report_path = os.path.join(folder_path, "meta_report")
    if os.path.isdir(meta_report_path):
        for filename in sorted(os.listdir(meta_report_path)):
            if _is_excluded_report_xlsx(filename):
                continue
            yield os.path.join(meta_report_path, filename)
    for dirpath, _, filenames in os.walk(folder_path):
        for filename in sorted(filenames):
            if _is_excluded_report_xlsx(filename):
                continue
            yield os.path.join(dirpath, filename)


def find_test_report(folder_path):
    """查找 DOU 场景报告 xlsx：优先 testReport.xlsx，否则选含 report 工作表的其它 xlsx。"""
    if not folder_path or not os.path.isdir(folder_path):
        return None

    # 1) 精确匹配 testReport.xlsx（meta_report 优先）
    meta_report_path = os.path.join(folder_path, "meta_report")
    if os.path.isdir(meta_report_path):
        for filename in os.listdir(meta_report_path):
            if filename.lower() == "testreport.xlsx":
                path = os.path.join(meta_report_path, filename)
                if _xlsx_has_report_sheet(path):
                    return path
    for dirpath, _, filenames in os.walk(folder_path):
        for filename in filenames:
            if filename.lower() == "testreport.xlsx":
                path = os.path.join(dirpath, filename)
                if _xlsx_has_report_sheet(path):
                    return path

    # 2) 回退：其它含 report 工作表的 xlsx，按打分取最优
    best_path = None
    best_score = -1
    seen = set()
    for path in _iter_folder_xlsx(folder_path):
        norm = os.path.normcase(os.path.abspath(path))
        if norm in seen:
            continue
        seen.add(norm)
        score = _score_report_xlsx(path)
        if score > best_score:
            best_score = score
            best_path = path
    return best_path



def get_platform_logs(folder_path, platform):
    """获取指定平台和文件夹的日志文件"""
    log_files = []
    if not os.path.exists(folder_path):
        return log_files
    
    if platform == "高通":
        pattern = re.compile(r"kernellogcat", re.IGNORECASE)
    elif platform == "展锐":
        pattern = re.compile(r"kernel", re.IGNORECASE)
    elif platform == "MTK":
        # MTK平台支持两种格式：
        # 1. *_linli_666.txt - 日志转换后的格式
        # 2. kernellogcat-log.*(.gz) - 原始日志格式
        pattern_linli = re.compile(r".+_(\d{4})_(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})_linli_666\.txt$")
        pattern_kernellogcat = re.compile(r"kernellogcat-log\.\d{8}-\d{6}(?:\.I\d+)?(?:\.gz)?")
    else:
        return log_files
    
    for dirpath, _, filenames in os.walk(folder_path):
        for filename in filenames:
            if platform == "MTK":
                # 优先匹配 linli_666 格式
                match = pattern_linli.match(filename)
                if match:
                    try:
                        year, month, day, hour, minute, second = match.groups()
                        log_time = datetime(int(year), int(month), int(day), 
                                          int(hour), int(minute), int(second))
                        log_files.append({
                            "path": os.path.join(dirpath, filename),
                            "timestamp": log_time.timestamp(),
                            "datetime": log_time,
                            "extension": ".txt"
                        })
                    except:
                        continue
                # 再匹配 kernellogcat 格式
                elif pattern_kernellogcat.match(filename):
                    file_path = os.path.join(dirpath, filename)
                    try:
                        mtime = os.path.getmtime(file_path)
                        log_time = datetime.fromtimestamp(mtime)
                        ext = ".gz" if filename.endswith(".gz") else ".txt"
                        log_files.append({
                            "path": file_path,
                            "timestamp": log_time.timestamp(),
                            "datetime": log_time,
                            "extension": ext
                        })
                    except:
                        continue
            else:
                if not filename.endswith(".gz") and pattern.search(filename):
                    file_path = os.path.join(dirpath, filename)
                    try:
                        mtime = os.path.getmtime(file_path)
                        log_time = datetime.fromtimestamp(mtime)
                        log_files.append({
                            "path": file_path,
                            "timestamp": log_time.timestamp(),
                            "datetime": log_time,
                            "extension": os.path.splitext(filename)[1]
                        })
                    except:
                        continue
    
    log_files.sort(key=lambda x: x["timestamp"])
    return log_files


def extract_suffix(name):
    """从名称中提取数字后缀"""
    if not isinstance(name, str):
        name = str(name)
    
    name = name.strip()
    match = re.search(r"_(\d+)$", name)
    if match:
        return match.group(1)
    return None


def is_screen_off_scene(desc, name=""):
    """判断场景是否为灭屏（与 TopN --screen 筛选逻辑一致）。"""
    d = str(desc or "")
    n = str(name or "")
    t = f"{d}\n{n}".lower()
    return (
        ("灭屏" in d)
        or ("熄屏" in d)
        or ("screen off" in t)
        or ("screen_off" in t)
        or ("screen-off" in t)
        or (" display off" in t)
        or ("display off" in t)
    )


def scene_screen_label(desc, name=""):
    """不含灭屏关键字的场景视为亮屏场景。"""
    return "灭屏" if is_screen_off_scene(desc, name) else "亮屏"


def mah_to_screen_current_impact_ma(power_diff_mah, total_screen_duration_sec):
    """单场景对亮/灭屏电流影响(mA) = 功耗差异mAh / 对应亮灭屏总时长(h)。"""
    try:
        mah = float(power_diff_mah)
    except (TypeError, ValueError):
        return None
    try:
        total_sec = float(total_screen_duration_sec)
    except (TypeError, ValueError):
        return None
    if total_sec <= 0:
        return None
    return round(mah * 3600.0 / total_sec, 4)


SCREEN_ON_SUBDIR = "screen_on"
SCREEN_OFF_SUBDIR = "screen_off"
SCREEN_BUCKET_SPECS = (
    ("on", "亮屏", SCREEN_ON_SUBDIR),
    ("off", "灭屏", SCREEN_OFF_SUBDIR),
)


def norm_screen_bucket(screen: str) -> str:
    """将 亮屏/灭屏/off/on 等归一为 on/off；无效返回空串。"""
    s = str(screen or "").strip()
    if not s:
        return ""
    s_low = s.lower()
    if s in ("灭屏", "熄屏") or s_low in ("off", "screen_off", "screen-off"):
        return "off"
    if s in ("亮屏",) or s_low in ("on", "screen_on", "screen-on"):
        return "on"
    return ""


def screen_bucket_label(bucket: str) -> str:
    for bid, label, _ in SCREEN_BUCKET_SPECS:
        if bid == bucket:
            return label
    return ""


def screen_results_subdir(screen: str) -> str:
    """亮屏 -> screen_on，灭屏 -> screen_off；未指定 screen 返回空串（用 high 根目录）。"""
    bucket = norm_screen_bucket(screen)
    if bucket == "on":
        return SCREEN_ON_SUBDIR
    if bucket == "off":
        return SCREEN_OFF_SUBDIR
    return ""


def screen_results_dir(high_dir: str, screen: str, *, create: bool = True) -> str:
    """高功耗目录下亮/灭屏产物子目录绝对路径。"""
    import os

    high = os.path.abspath(str(high_dir).strip())
    sub = screen_results_subdir(screen)
    if not sub:
        return high
    path = os.path.join(high, sub)
    if create:
        os.makedirs(path, exist_ok=True)
    return path


def _safe_float_cell(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def default_ignorable_scenes_path():
    from paths import IGNORABLE_SCENES_JSON

    return IGNORABLE_SCENES_JSON


def load_ignorable_scenes_config(config_path=None):
    """加载可忽略场景配置。文件不存在或 rules 为空时返回空规则。"""
    path = Path(config_path) if config_path else default_ignorable_scenes_path()
    path = path.resolve()
    if not path.exists():
        return {"path": str(path), "default_reason": "脚本问题", "rules": []}

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"path": str(path), "default_reason": "脚本问题", "rules": []}

    if isinstance(raw, list):
        rules = []
        for item in raw:
            if isinstance(item, (int, float)):
                rules.append({"suffix": str(int(item))})
            elif isinstance(item, str):
                s = item.strip()
                if s.isdigit():
                    rules.append({"suffix": s})
                elif ":" in s:
                    kind, val = s.split(":", 1)
                    kind = kind.strip().lower()
                    val = val.strip()
                    if kind in ("suffix", "name", "desc"):
                        rules.append({kind: val})
                    elif kind in ("name_contains", "desc_contains"):
                        rules.append({kind: val})
                else:
                    rules.append({"suffix": s})
        return {"path": str(path), "default_reason": "脚本问题", "rules": rules}

    if not isinstance(raw, dict):
        return {"path": str(path), "default_reason": "脚本问题", "rules": []}

    rules = raw.get("rules") or raw.get("scenes") or []
    if not isinstance(rules, list):
        rules = []
    return {
        "path": str(path),
        "default_reason": str(raw.get("default_reason") or "脚本问题").strip() or "脚本问题",
        "rules": rules,
    }


def scene_matches_ignorable_rule(name, desc, suffix, rule):
    if not isinstance(rule, dict):
        if isinstance(rule, (int, float)):
            return str(suffix) == str(int(rule))
        if isinstance(rule, str):
            rs = rule.strip()
            return rs and (str(suffix) == rs or rs in str(name) or rs in str(desc))
        return False

    name_s = str(name or "").strip()
    desc_s = str(desc or "").strip()
    suf_s = str(suffix or "").strip()

    if "suffix" in rule and str(rule.get("suffix", "")).strip():
        if suf_s == str(rule["suffix"]).strip():
            return True
    if "name" in rule and str(rule.get("name", "")).strip():
        if name_s == str(rule["name"]).strip():
            return True
    if "name_contains" in rule and str(rule.get("name_contains", "")).strip():
        if str(rule["name_contains"]).strip() in name_s:
            return True
    if "desc" in rule and str(rule.get("desc", "")).strip():
        if desc_s == str(rule["desc"]).strip():
            return True
    if "desc_contains" in rule and str(rule.get("desc_contains", "")).strip():
        if str(rule["desc_contains"]).strip() in desc_s:
            return True
    return False


def is_ignorable_scene(name, desc, suffix, ignorable_config):
    rules = ignorable_config.get("rules") or []
    for rule in rules:
        if scene_matches_ignorable_rule(name, desc, suffix, rule):
            return True
    return False


def ignorable_scene_reason(name, desc, suffix, ignorable_config):
    rules = ignorable_config.get("rules") or []
    default_reason = ignorable_config.get("default_reason") or "脚本问题"
    for rule in rules:
        if not scene_matches_ignorable_rule(name, desc, suffix, rule):
            continue
        if isinstance(rule, dict) and str(rule.get("reason") or "").strip():
            return str(rule["reason"]).strip()
    return default_reason


def parse_top_scenes_json(payload):
    """解析 topn_scenes JSON：兼容 list（旧）与 {top_scenes, ignored_scenes}（新）。"""
    if isinstance(payload, list):
        return payload, [], None
    if isinstance(payload, dict):
        top = payload.get("top_scenes") or []
        ignored = payload.get("ignored_scenes") or []
        if not isinstance(top, list):
            top = []
        if not isinstance(ignored, list):
            ignored = []
        return top, ignored, payload
    return [], [], None


AUTO_ERROR_RULE_PREFIX = "excel_error:"
AUTO_ERROR_DEFAULT_REASON = "脚本问题（testReport 场景执行 error，非版本功耗回归）"
IGNORABLE_AUTO_SESSION_FILENAME = "ignorable_auto_session.json"


def _auto_error_rule_key(name: str) -> str:
    return f"{AUTO_ERROR_RULE_PREFIX}{str(name or '').strip()}"


def resolve_high_dir_from_artifact(path) -> Path:
    """从 topn/results/html 等产物路径反推 high 根目录。"""
    p = Path(path).resolve()
    if p.parent.name in (SCREEN_ON_SUBDIR, SCREEN_OFF_SUBDIR):
        return p.parent.parent
    return p.parent


DOU_LOW_ROOT = r"\\10.205.4.20\sw_temp\底软通信开发部\lzx\DOUtestPASS数据"
DOU_HIGH_ROOT = r"\\10.205.4.20\sw_temp\底软通信开发部\lzx\DOU高功耗文件夹"
META_LOW_JSON_FILES = (
    "dou_prepare_result.json",
    "scene_compare_result.json",
    "power_analysis_result.json",
)

_low_smb_candidates: list[str] | None = None


def _cached_low_candidates() -> list[str]:
    global _low_smb_candidates
    if _low_smb_candidates is None:
        _low_smb_candidates = _find_dou_data_dirs(DOU_LOW_ROOT, max_depth=8)
    return _low_smb_candidates


def _is_dou_data_dir(dir_path) -> bool:
    folder = str(dir_path or "").strip()
    if not folder or not os.path.isdir(folder):
        return False
    if find_test_report(folder):
        return True
    meta = os.path.join(folder, "meta_report")
    if os.path.isdir(meta):
        for filename in os.listdir(meta):
            if _is_excluded_report_xlsx(filename):
                continue
            if filename.lower().endswith(".xlsx"):
                return True
    return False


def _find_dou_data_dirs(root, max_depth: int = 8) -> list[str]:
    root = str(root or "").strip()
    if not root or not os.path.isdir(root):
        return []
    found: list[str] = []
    queue: list[tuple[str, int]] = [(root, 0)]
    while queue:
        current, depth = queue.pop(0)
        if depth > max_depth:
            continue
        try:
            entries = os.listdir(current)
        except OSError:
            continue
        for name in entries:
            path = os.path.join(current, name)
            if not os.path.isdir(path):
                continue
            if _is_dou_data_dir(path):
                found.append(os.path.abspath(path))
            if depth < max_depth:
                queue.append((path, depth + 1))
    return list(dict.fromkeys(found))


def _parse_high_dir_hints(high_dir) -> dict:
    """从 high 目录名提取项目/SN/版本线索（无 JIRA 时的 SMB 低功耗匹配）。"""
    text = Path(high_dir).name
    hints: dict[str, str | None] = {
        "project": None,
        "compare_os": None,
        "high_os": None,
        "sn": None,
    }
    m = re.search(r"\b(X\d+[A-Z0-9]{2,})\b", text, re.I)
    if m:
        hints["project"] = m.group(1).upper()
    if not hints["project"]:
        m = re.search(r"\b(CN\d+[A-Z]?)\b", text, re.I)
        if m:
            hints["project"] = m.group(1).upper()
    if not hints["project"]:
        m = re.search(r"\b(LK7[Kk]?)\b", text, re.I)
        if m:
            hints["project"] = m.group(1).upper()
    m = re.search(r"\b(\d+\.\d+\.\d+\.\d+)\b", text)
    if m:
        hints["high_os"] = m.group(1)
    m = re.search(r"SN(\d{10,}[A-Z0-9]*)", text, re.I)
    if m:
        hints["sn"] = m.group(1)
    elif (m := re.search(r"CC(\d{12,})", text, re.I)):
        hints["sn"] = f"CC{m.group(1)}"
    return hints


def _score_low_candidate(path: str, hints: dict, high_path: str) -> int:
    score = 0
    name = os.path.basename(path)
    full = path.replace("/", "\\")
    high_norm = os.path.abspath(str(high_path or ""))
    path_norm = os.path.abspath(path)
    if high_norm and (path_norm == high_norm or path_norm.startswith(high_norm + os.sep)):
        return -1000
    high_root = DOU_HIGH_ROOT.replace("/", "\\")
    if high_root.lower() in full.lower():
        return -1000
    phone_logs = os.path.join(path, "phone_logs")
    if os.path.isdir(phone_logs):
        if any(f.lower().startswith("mobile_log") and f.lower().endswith(".zip") for f in os.listdir(phone_logs)):
            score += 8
        elif any(
            os.path.isdir(os.path.join(phone_logs, f)) and f.lower().startswith("mobile_log")
            for f in os.listdir(phone_logs)
        ):
            score += 6
    project = hints.get("project")
    if project and re.search(re.escape(str(project)), full, re.I):
        score += 12
    compare_os = hints.get("compare_os")
    if compare_os and (
        re.search(re.escape(str(compare_os)), name, re.I)
        or re.search(rf"tOS{re.escape(str(compare_os))}", full, re.I)
    ):
        score += 15
    sn = hints.get("sn")
    if sn and re.search(re.escape(str(sn)), full, re.I):
        score += 8
    if re.search(r"PowerMonitor|PASS|pass", name):
        score += 5
    high_os = hints.get("high_os")
    if high_os and (
        re.search(re.escape(str(high_os)), name, re.I)
        or re.search(rf"tOS{re.escape(str(high_os))}", full, re.I)
    ):
        score -= 10
    if re.search(r"dou3", name, re.I):
        score += 2
    if DOU_LOW_ROOT.replace("/", "\\").lower() in full.lower():
        score += 3
    return score


def match_low_dir_in_smb(high_dir) -> str | None:
    """在 DOUtestPASS数据 下按 high 目录名线索自动匹配低功耗目录。"""
    high = os.path.abspath(str(high_dir).strip())
    if not os.path.isdir(high):
        return None
    hints = _parse_high_dir_hints(high)
    candidates = _cached_low_candidates()
    ranked = sorted(
        ((p, _score_low_candidate(p, hints, high)) for p in candidates),
        key=lambda x: x[1],
        reverse=True,
    )
    for path, score in ranked:
        if score > 0:
            return path
    return None


def _low_from_meta_json(high: Path) -> str | None:
    for name in META_LOW_JSON_FILES:
        meta_path = high / name
        if not meta_path.is_file():
            continue
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        low = str(data.get("low") or "").strip()
        if low and Path(low).is_dir():
            return low
    return None


def resolve_low_dir_from_high(high_dir) -> str | None:
    """读取落盘 JSON 中的 low；无效时在 DOUtestPASS数据 下自动匹配。"""
    high = Path(high_dir).resolve()
    low = _low_from_meta_json(high)
    if low:
        return low
    return match_low_dir_in_smb(high)


def read_test_report_error_scenes(folder_path) -> list[dict]:
    """读取 testReport.xlsx report 表中 result=error 的场景。"""
    folder = str(folder_path or "").strip()
    if not folder or not os.path.isdir(folder):
        return []

    report_path = find_test_report(folder)
    if not report_path:
        return []

    try:
        df = pd.read_excel(report_path, sheet_name="report")
    except Exception:
        return []

    if "result" not in df.columns:
        return []

    mask = df["result"].astype(str).str.strip().str.lower().eq("error")
    scenes: list[dict] = []
    seen_names: set[str] = set()
    for _, row in df[mask].iterrows():
        name = str(row.get("name", "")).strip()
        if not name or name in seen_names:
            continue
        seen_names.add(name)
        scenes.append(
            {
                "name": name,
                "desc": str(row.get("desc", "") or "").strip(),
                "suffix": extract_suffix(name),
                "error_msg": str(row.get("error_msg", "") or "").strip(),
                "source_folder": folder,
                "source_report": report_path,
            }
        )
    return scenes


def collect_excel_error_scenes(high_dir, low_dir=None) -> list[dict]:
    """合并 high/low 两侧 testReport 中的 error 场景（按 name 去重）。"""
    merged: list[dict] = []
    seen_names: set[str] = set()
    folders = [high_dir]
    if low_dir:
        folders.append(low_dir)
    for folder in folders:
        for scene in read_test_report_error_scenes(folder):
            name = scene.get("name") or ""
            if not name or name in seen_names:
                continue
            seen_names.add(name)
            merged.append(scene)
    return merged


def _read_ignorable_json(path: Path) -> dict:
    if not path.exists():
        return {
            "description": "",
            "default_reason": "脚本问题",
            "rules": [],
        }
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"description": "", "default_reason": "脚本问题", "rules": []}
    if not isinstance(raw, dict):
        return {"description": "", "default_reason": "脚本问题", "rules": []}
    rules = raw.get("rules") or raw.get("scenes") or []
    if not isinstance(rules, list):
        rules = []
    raw["rules"] = rules
    return raw


def _write_ignorable_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _ignorable_auto_session_path(high_dir) -> Path:
    return Path(high_dir).resolve() / IGNORABLE_AUTO_SESSION_FILENAME


def _strip_auto_error_rules(rules: list) -> tuple[list, int]:
    """移除带 excel_error 自动标记的规则，保留手动配置。"""
    kept = [
        rule
        for rule in rules
        if not (
            isinstance(rule, dict)
            and str(rule.get("_auto_key") or "").startswith(AUTO_ERROR_RULE_PREFIX)
        )
    ]
    return kept, len(rules) - len(kept)


def clear_auto_error_ignorable_rules(high_dir, config_path=None) -> int:
    """分析结束后移除本次自动写入 ignorable_scenes.json 的规则。"""
    high = Path(high_dir).resolve()
    config = Path(config_path) if config_path else default_ignorable_scenes_path()
    config = config.resolve()
    session_path = _ignorable_auto_session_path(high)

    keys_to_remove: set[str] = set()
    if session_path.exists():
        try:
            session = json.loads(session_path.read_text(encoding="utf-8"))
            added_rules = session.get("added_rules") or []
            keys_to_remove = {
                str(rule.get("_auto_key")).strip()
                for rule in added_rules
                if isinstance(rule, dict) and str(rule.get("_auto_key") or "").strip()
            }
        except Exception:
            pass
        session_path.unlink(missing_ok=True)

    if not config.exists():
        return 0

    raw = _read_ignorable_json(config)
    rules = raw.get("rules") or []
    if keys_to_remove:
        kept = [
            rule
            for rule in rules
            if not (
                isinstance(rule, dict)
                and str(rule.get("_auto_key") or "").strip() in keys_to_remove
            )
        ]
    else:
        # 无 session 或 session 为空时，兜底清除全部 testReport error 临时规则
        kept, _ = _strip_auto_error_rules(rules)
    removed = len(rules) - len(kept)
    raw["rules"] = kept
    _write_ignorable_json(config, raw)
    return removed


def apply_auto_error_ignorable_rules(high_dir, low_dir=None, config_path=None) -> dict:
    """
    读取 high/low testReport 中 result=error 的场景，临时写入 ignorable_scenes.json。
    返回 {added, error_scenes, session_path}；分析结束需调用 clear_auto_error_ignorable_rules。
    """
    high = Path(high_dir).resolve()
    config = Path(config_path) if config_path else default_ignorable_scenes_path()
    config = config.resolve()
    session_path = _ignorable_auto_session_path(high)

    if session_path.exists():
        clear_auto_error_ignorable_rules(high, config)

    low = str(low_dir).strip() if low_dir else resolve_low_dir_from_high(high)
    error_scenes = collect_excel_error_scenes(high, low)

    raw = _read_ignorable_json(config)
    rules = list(raw.get("rules") or [])
    # 每次分析先清掉历史 testReport error 临时规则，避免跨任务残留
    rules, _stripped = _strip_auto_error_rules(rules)
    manual_name_contains = {
        str(rule.get("name_contains")).strip()
        for rule in rules
        if isinstance(rule, dict) and str(rule.get("name_contains") or "").strip()
    }

    added_rules: list[dict] = []
    for scene in error_scenes:
        name = str(scene.get("name") or "").strip()
        if not name:
            continue
        auto_key = _auto_error_rule_key(name)
        if name in manual_name_contains:
            continue
        rule = {
            "name_contains": name,
            "reason": AUTO_ERROR_DEFAULT_REASON,
            "_auto_key": auto_key,
        }
        err_msg = str(scene.get("error_msg") or "").strip()
        if err_msg:
            rule["_error_msg"] = err_msg[:300]
        rules.append(rule)
        added_rules.append(rule)
        manual_name_contains.add(name)

    raw["rules"] = rules
    _write_ignorable_json(config, raw)

    session_payload = {
        "high": str(high),
        "low": low or "",
        "added_rules": added_rules,
        "error_scenes": error_scenes,
    }
    session_path.write_text(
        json.dumps(session_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        "added": len(added_rules),
        "error_scenes": error_scenes,
        "session_path": str(session_path),
    }


def build_suffix_mapping(all_names):
    """构建后缀映射关系"""
    suffix_mapping = {}
    for name in all_names:
        suffix = extract_suffix(name)
        if suffix:
            if suffix not in suffix_mapping:
                suffix_mapping[suffix] = []
            suffix_mapping[suffix].append(name)
    
    all_suffixes = sorted(suffix_mapping.keys(), key=lambda x: int(x))
    return suffix_mapping, all_suffixes


class CacheManager:
    """缓存管理器"""
    def generate_analyzer_cache_key(self, suffix, scene1_logs, scene2_logs):
        """生成分析器缓存键（类似tkinter版本）"""
        import hashlib
        
        # 提取日志文件信息（最多前5个）
        scene1_info = []
        for i, log in enumerate(scene1_logs[:5]):
            log_path = log.get('path', '')
            timestamp = log.get('timestamp', 0)
            filename = os.path.basename(log_path) if log_path else f'log{i}'
            scene1_info.append(f"{filename}:{timestamp}")
        
        scene2_info = []
        for i, log in enumerate(scene2_logs[:5]):
            log_path = log.get('path', '')
            timestamp = log.get('timestamp', 0)
            filename = os.path.basename(log_path) if log_path else f'log{i}'
            scene2_info.append(f"{filename}:{timestamp}")
        
        key_data = f"cpu_analyzer:{suffix}:{','.join(scene1_info)}:{','.join(scene2_info)}"
        return hashlib.md5(key_data.encode()).hexdigest()
    
    def get_cache_stats(self):
        """获取缓存统计信息"""
        cache_files = []
        if os.path.exists(self.cache_dir):
            for filename in os.listdir(self.cache_dir):
                if filename.endswith('.pkl'):
                    filepath = os.path.join(self.cache_dir, filename)
                    cache_files.append(filepath)
        
        total_size = sum(os.path.getsize(f) for f in cache_files)
        
        return {
            'cache_count': len(cache_files),
            'cache_size_bytes': total_size,
            'cache_size_mb': total_size / (1024 * 1024)
        }
    
    def clear_pattern(self, pattern):
            """按模式清除缓存文件"""
            import fnmatch
            deleted_count = 0
            
            for filename in os.listdir(self.cache_dir):
                if fnmatch.fnmatch(filename, pattern + "*.pkl"):
                    try:
                        os.remove(os.path.join(self.cache_dir, filename))
                        deleted_count += 1
                    except:
                        pass
            
            return deleted_count
    def __init__(self, cache_dir="./cache"):
        self.cache_dir = cache_dir
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir, exist_ok=True)
    
    def get_cache_key(self, data):
        """生成缓存键"""
        if isinstance(data, dict):
            data_str = json.dumps(data, sort_keys=True)
        else:
            data_str = str(data)
        
        return hashlib.md5(data_str.encode()).hexdigest()
    
    def get(self, key, max_age_hours=24):
        """从缓存获取数据"""
        cache_file = os.path.join(self.cache_dir, f"{key}.pkl")
        
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'rb') as f:
                    cache_data = pickle.load(f)
                
                # 检查缓存是否过期
                cache_time = cache_data.get('timestamp')
                if cache_time and (datetime.now() - cache_time).total_seconds() < max_age_hours * 3600:
                    return cache_data.get('data')
            except:
                pass
        
        return None
    
    def set(self, key, data):
        """保存数据到缓存"""
        cache_file = os.path.join(self.cache_dir, f"{key}.pkl")
        
        cache_data = {
            'timestamp': datetime.now(),
            'data': data
        }
        
        try:
            with open(cache_file, 'wb') as f:
                pickle.dump(cache_data, f)
            return True
        except:
            return False
    
    def clear(self, key=None):
        """清除缓存"""
        if key:
            cache_file = os.path.join(self.cache_dir, f"{key}.pkl")
            if os.path.exists(cache_file):
                os.remove(cache_file)
        else:
            for filename in os.listdir(self.cache_dir):
                if filename.endswith('.pkl'):
                    os.remove(os.path.join(self.cache_dir, filename))
    
    def check_suffix_cache(self, suffix, app_state):
        """检查指定后缀是否有缓存"""
        try:
            # 检查内存缓存
            cache_key = f"cpu_analysis_{suffix}"
            has_memory_cache = cache_key in app_state.analysis_cache
            
            # 检查文件缓存
            cache_key_data = {
                "suffix": suffix,
                "scene1_folder": app_state.scene1_folder,
                "scene2_folder": app_state.scene2_folder,
                "scene1_platform": app_state.scene1_platform,
                "scene2_platform": app_state.scene2_platform
            }
            cache_file_key = self.get_cache_key(cache_key_data)
            has_file_cache = self.get(cache_file_key) is not None
            
            return {
                'success': True,
                'suffix': suffix,
                'has_cache': has_memory_cache or has_file_cache,
                'memory_cache': has_memory_cache,
                'file_cache': has_file_cache,
                'message': f'后缀_{suffix} {"有" if has_memory_cache or has_file_cache else "无"}缓存'
            }
        except Exception as e:
            return {
                'success': False,
                'message': f'检查缓存失败: {str(e)}'
            }
    
    def get_cache_statistics(self):
        """获取缓存统计信息"""
        cache_stats = {}
        cache_dirs = [str(CPU_CACHE_DIR), './analysis_cache', './uploads/converted_logs']
        
        for cache_dir in cache_dirs:
            if os.path.exists(cache_dir):
                file_count = 0
                total_size = 0
                for filename in os.listdir(cache_dir):
                    filepath = os.path.join(cache_dir, filename)
                    if os.path.isfile(filepath):
                        file_count += 1
                        total_size += os.path.getsize(filepath)
                
                cache_stats[cache_dir] = {
                    'file_count': file_count,
                    'total_size': total_size
                }
            else:
                cache_stats[cache_dir] = {
                    'file_count': 0,
                    'total_size': 0
                }
        
        return cache_stats
    
    def get_converted_files(self, output_dir):
        """获取转换后的文件列表"""
        converted_files = []
        if os.path.exists(output_dir):
            for filename in os.listdir(output_dir):
                filepath = os.path.join(output_dir, filename)
                if os.path.isfile(filepath):
                    converted_files.append({
                        'name': filename,
                        'path': filepath,
                        'size': os.path.getsize(filepath),
                        'modified': os.path.getmtime(filepath)
                    })
        return converted_files


def format_file_size(size_bytes):
    """格式化文件大小"""
    if size_bytes == 0:
        return "0 B"
    
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    unit_index = 0
    
    while size_bytes >= 1024 and unit_index < len(units) - 1:
        size_bytes /= 1024.0
        unit_index += 1
    
    return f"{size_bytes:.2f} {units[unit_index]}"


def safe_read_excel(file_path, **kwargs):
    """安全读取Excel文件"""
    try:
        return pd.read_excel(file_path, **kwargs)
    except Exception as e:
        print(f"读取Excel文件失败: {str(e)}")
        return None


def is_kernel_log_file(filename):
    """检查是否为 kernel 日志文件（含 .curf，如 kernel_log_2026_0128_021444.curf）。"""
    if '_linli_666' in str(filename).lower():
        return False
    pattern = r'^kernel_log_(?:.+_)?(\d{4})_(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})(\.curf)?$'
    return re.match(pattern, filename, re.IGNORECASE) is not None


def parse_time_from_kernel_filename(filename):
    """从kernel日志文件名解析时间"""
    pattern = r'^kernel_log_(?:.+_)?(\d{4})_(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})(\.curf)?$'
    match = re.match(pattern, filename, re.IGNORECASE)
    
    if not match:
        return None
    
    try:
        year = int(match.group(1))
        month = int(match.group(2))
        day = int(match.group(3))
        hour = int(match.group(4))
        minute = int(match.group(5))
        second = int(match.group(6))
        extension = match.group(7) or ""
        
        return {
            'year': year,
            'month': month,
            'day': day,
            'hour': hour,
            'minute': minute,
            'second': second,
            'extension': extension,
            'datetime': datetime(year, month, day, hour, minute, second)
        }
    except:
        return None


def find_kernel_logs_in_folder(folder_path, recursive=True):
    """在文件夹中查找kernel日志文件"""
    kernel_files = []
    
    if recursive:
        for root, dirs, files in os.walk(folder_path):
            for filename in files:
                if is_kernel_log_file(filename):
                    file_path = os.path.join(root, filename)
                    time_info = parse_time_from_kernel_filename(filename)
                    
                    if time_info:
                        kernel_files.append({
                            'path': file_path,
                            'filename': filename,
                            'relative_path': os.path.relpath(file_path, folder_path),
                            'time_info': time_info,
                            'size': os.path.getsize(file_path) if os.path.exists(file_path) else 0
                        })
    else:
        for filename in os.listdir(folder_path):
            file_path = os.path.join(folder_path, filename)
            if os.path.isfile(file_path) and is_kernel_log_file(filename):
                time_info = parse_time_from_kernel_filename(filename)
                
                if time_info:
                    kernel_files.append({
                        'path': file_path,
                        'filename': filename,
                        'relative_path': filename,
                        'time_info': time_info,
                        'size': os.path.getsize(file_path) if os.path.exists(file_path) else 0
                    })
    
    # 按时间排序
    kernel_files.sort(key=lambda x: x['time_info']['datetime'])
    
    return kernel_files


def convert_log_time_wrapper(input_file, output_file, script_path, time_offset):
    """包装日志时间转换脚本调用"""
    try:
        import subprocess
        
        # 调用脚本进行转换
        result = subprocess.run(
            [sys.executable, script_path, input_file, str(time_offset), output_file],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        return {
            'success': result.returncode == 0,
            'stdout': result.stdout,
            'stderr': result.stderr,
            'returncode': result.returncode
        }
    except subprocess.TimeoutExpired:
        return {
            'success': False,
            'stdout': '',
            'stderr': '脚本执行超时（30秒）',
            'returncode': -1
        }
    except Exception as e:
        return {
            'success': False,
            'stdout': '',
            'stderr': f'执行失败: {str(e)}',
            'returncode': -1
        }