#!/usr/bin/env python3
"""Align AudioMix intervals with DOU scene windows and flag anomalies."""

from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

SUFFIX_RE = re.compile(r"_(\d+)$")


def _format_ms(ms: int) -> str:
    if ms < 0:
        ms = 0
    if ms < 1000:
        return f"{ms}ms"
    sec = ms // 1000
    ms_rem = ms % 1000
    parts: List[str] = []
    h, sec = divmod(sec, 3600)
    m, sec = divmod(sec, 60)
    if h:
        parts.append(f"{h}h")
    if m:
        parts.append(f"{m}m")
    if sec or ms_rem:
        if ms_rem:
            parts.append(f"{sec}.{ms_rem:03d}s")
        else:
            parts.append(f"{sec}s")
    return " ".join(parts) if parts else "0ms"

# longwake overlap threshold (ms); None = media-like scenes allow long holds
CATEGORY_THRESHOLDS_MS: Dict[str, Optional[int]] = {
    "screen_off": 60_000,
    "screen_off_music": None,
    "idle_home": 10_000,
    "feed_scroll": 60_000,
    "document": 30_000,
    "camera": 30_000,
    "store_download": 30_000,
    "web_browse": 120_000,
    "maps_nav": 300_000,
    "game": 60_000,
    "voice_call": 5_000,
    "general_on": 180_000,
    "media": None,
}

CATEGORY_REASONS: Dict[str, str] = {
    "screen_off": "灭屏场景不应长时间 AudioMix 持锁",
    "screen_off_music": "灭屏听音乐/音频场景允许播放应用持锁",
    "idle_home": "主页/待机场景不应出现 AudioMix 持锁",
    "feed_scroll": "Feed/滑动浏览场景不应长时间后台音频持锁",
    "document": "文档浏览场景不应长时间 AudioMix 持锁",
    "camera": "相机/图库场景不应长时间 AudioMix 持锁",
    "store_download": "应用商店/下载场景不应长时间 AudioMix 持锁",
    "web_browse": "网页浏览场景不应长时间 AudioMix 持锁",
    "maps_nav": "地图导航场景持锁应来自导航/语音服务，超长持锁异常",
    "game": "游戏场景不应长时间 AudioMix 持锁（非游戏应用后台音频异常）",
    "voice_call": "通话场景持锁应来自电话/拨号应用或系统，不应为其他应用后台音频",
    "general_on": "非音视频亮屏场景不应长时间 AudioMix 持锁",
}

CATEGORY_PLAUSIBLE_OWNERS: Dict[str, Optional[Set[str]]] = {
    "screen_off": {"system"},
    "screen_off_music": {"media", "system"},
    "idle_home": {"system"},
    "media": {"media", "system"},
    "maps_nav": {"maps", "system"},
    "feed_scroll": {"social", "media", "browser", "system"},
    "document": {"office", "browser", "system"},
    "camera": {"camera", "system"},
    "store_download": {"store", "system"},
    "web_browse": {"browser", "media", "system"},
    "game": {"game", "system"},
    "voice_call": {"telecom", "system"},
    "general_on": None,
}

CROSS_DENY_RULES: List[Tuple[Set[str], Set[str], int, str]] = [
    (
        {"camera", "document", "store_download", "idle_home", "screen_off"},
        {"media", "social", "game"},
        1_000,
        "非播放/社交场景不应由音视频/社交应用 {pkg} 持锁",
    ),
    (
        {"media"},
        {"store", "office", "camera", "game", "maps"},
        3_000,
        "音视频播放场景持锁方应为播放/音频类应用，当前为 {pkg}",
    ),
    (
        {"maps_nav"},
        {"media", "social", "game", "store", "office"},
        3_000,
        "导航场景持锁方应为地图/导航或系统语音，当前为 {pkg}",
    ),
    (
        {"media"},
        {"social"},
        3_000,
        "播放/音视频场景持锁应为播放/音频类应用，当前为 {pkg}",
    ),
    (
        {"voice_call"},
        {"media", "social", "game", "store", "office", "maps", "browser"},
        1_000,
        "通话场景持锁方应为电话/拨号或系统，当前为 {pkg}",
    ),
    (
        {"camera"},
        {"media", "maps", "social", "browser", "game", "store", "office"},
        1_000,
        "相机/图库场景不应由 {pkg} 持 AudioMix",
    ),
    (
        {"document", "store_download"},
        {"media", "game", "social"},
        3_000,
        "文档/下载场景不应由 {pkg} 持 AudioMix",
    ),
    (
        {"feed_scroll"},
        {"store", "office", "camera", "maps"},
        5_000,
        "Feed 滑动场景不应由 {pkg} 持 AudioMix",
    ),
    (
        {"game"},
        {"media", "social", "browser", "store", "office", "maps"},
        3_000,
        "游戏场景不应由 {pkg} 持 AudioMix（应为游戏本身或系统服务）",
    ),
]

OWNER_CLASSIFIERS: List[Tuple[str, re.Pattern[str]]] = [
    (
        "telecom",
        re.compile(
            r"dialer|incallui|telecom|server\.telecom|phone\.call|com\.android\.phone",
            re.I,
        ),
    ),
    (
        "system",
        re.compile(
            r"audioserver|media\.codec|mediaserver|systemui|system_server|"
            r"android\.system|1041|1013|1021|\bradio\b",
            re.I,
        ),
    ),
    (
        "media",
        re.compile(
            r"youtube|music|spotify|mxtech|videoplayer|tiktok|douyin|bilibili|"
            r"aweme|trill|musically|snssdk|"
            r"netflix|iqiyi|youku|tencent\.qqmusic|kugou|kuwo|nubia\.music|"
            r"miui\.player|heytap\.music|soundrecorder|audio|radio\.fm|podcast",
            re.I,
        ),
    ),
    (
        "maps",
        re.compile(
            r"maps|waze|navigation|autonavi|amap|baidu\.map|navi|here\.|tomtom",
            re.I,
        ),
    ),
    (
        "browser",
        re.compile(
            r"chrome|browser|webview|firefox|opera|edge|brave|safari|ucbrowser|"
            r"miui\.browser|heytap\.browser",
            re.I,
        ),
    ),
    (
        "camera",
        re.compile(
            r"camera|gallery|photos|miui\.gallery|google\.android\.apps\.photos|"
            r"mediaeditor|snapcam",
            re.I,
        ),
    ),
    (
        "store",
        re.compile(
            r"finsky|vending|appmarket|appstore|packageinstaller|"
            r"heytap\.market|miui\.packageinstaller|install",
            re.I,
        ),
    ),
    (
        "social",
        re.compile(
            r"facebook|instagram|twitter|reddit|whatsapp|telegram|"
            r"wechat|tencent\.mm|weibo|snapchat|linkedin|pinterest|threads|"
            r"messenger|orca|shopee|flipkart|lazada|amazon\.shopping",
            re.I,
        ),
    ),
    (
        "office",
        re.compile(
            r"wps|office|word|excel|pdf|document|slides|onenote|"
            r"com\.kingsoft|microsoft\.office",
            re.I,
        ),
    ),
    (
        "game",
        re.compile(
            r"game|pubg|mihoyo|unity|roblox|epicgames|tencent\.tmgp|"
            r"activision|supercell|ludo|chess|block\.juggle|juggle|"
            r"blockblast|mobile\.legends|legends|freefire|codm|"
            r"king\.|supercell|miHoYo|garena",
            re.I,
        ),
    ),
]

MIN_OWNER_MISMATCH_MS = 3_000

# 包名 ↔ 场景描述常见别名（含 DOU 报告拼写变体 Whatapp）
APP_SCENE_ALIASES: Dict[str, Tuple[str, ...]] = {
    "whatsapp": ("whatsapp", "whatapp", "wa "),
    "com.whatsapp": ("whatsapp", "whatapp"),
    "orca": ("messenger", "facebook messenger"),
    "com.facebook.orca": ("messenger",),
    "aweme": ("tiktok", "抖音", "douyin"),
    "com.ss.android.ugc.aweme": ("tiktok", "抖音"),
    "youtube": ("youtube",),
    "com.google.android.youtube": ("youtube",),
    "mobile.legends": ("mlbb", "mobile legends", "mobile.legends", "legends"),
    "com.mobile.legends": ("mlbb", "mobile legends", "legends"),
    "block.juggle": ("block blast", "blockblast", "block"),
    "com.block.juggle": ("block blast", "blockblast", "block"),
    "spotify": ("spotify", "music", "听音乐", "音乐"),
    "mxtech.videoplayer": ("mxplayer", "mxtech"),
    "com.mxtech.videoplayer.ad": ("mxplayer", "mxtech"),
    "com.google.android.dialer": ("dialer", "google dialer"),
    "com.android.dialer": ("dialer", "phone"),
    "com.android.incallui": ("incall", "phone", "通话"),
    "com.android.server.telecom": ("phone", "通话"),
    "pinterest": ("pinterest",),
    "com.pinterest": ("pinterest",),
}


def _scene_full_text(scene: dict) -> str:
    return f"{scene.get('desc') or ''} {scene.get('name') or ''}".strip()


def _scene_tokens(text: str) -> List[str]:
    """场景标题中的英文/数字词（用于与包名互匹配）。"""
    return [t for t in re.findall(r"[a-z0-9]{3,}", text.lower()) if t not in ("data", "wifi", "the", "and")]


def _is_intentional_audio_scene(scene_text: str) -> bool:
    return bool(
        re.search(
            r"听音乐|听广播|听书|music|spotify|音频|播客|podcast|radio|fm",
            scene_text,
            re.I,
        )
    )


def _owner_belongs_to_scene(owner_label: str, scene: dict) -> bool:
    """持锁包名与场景描述/标题一致 → 本场景内持锁合理（优先于分类规则）。"""
    scene_text = _scene_full_text(scene)
    if not scene_text:
        return False
    st = scene_text.lower()
    pkg = extract_package(owner_label)
    pkg_l = pkg.lower()

    if _owner_matches_scene_app(pkg, scene_text):
        return True

    # 包名片段 ↔ 场景英文词互相包含（block↔Block Blast, legends↔MLBB 已由 alias 覆盖）
    pkg_parts = _pkg_name_tokens(pkg_l)
    scene_parts = _scene_tokens(st)
    for pp in pkg_parts:
        if len(pp) >= 3 and pp in st:
            return True
    for sp in scene_parts:
        if len(sp) >= 3 and sp in pkg_l:
            return True
    if pkg_parts and scene_parts:
        if len(set(pkg_parts) & set(scene_parts)) >= 1:
            return True

    # 游戏场景 + 游戏包
    if re.search(r"游戏|game|mlbb|pubg|play", st, re.I):
        if classify_owner(owner_label) == "game" or _game_scene_owner_ok(owner_label, scene_text):
            return True

    # 灭屏听音乐等：媒体应用持锁合理
    if _is_intentional_audio_scene(scene_text):
        if classify_owner(owner_label) in ("media", "system"):
            return True

    # 通话场景：仅对应通话/拨号应用或系统
    if _is_phone_call_scene(scene_text):
        return _owner_ok_for_call_scene(owner_label, scene_text)

    return False


def _pkg_name_tokens(pkg: str) -> List[str]:
    """从包名提取可用于场景匹配的英文/数字片段。"""
    pkg_l = pkg.lower()
    parts: List[str] = []
    for seg in pkg_l.replace("_", ".").split("."):
        if len(seg) >= 3 and seg not in ("com", "android", "google", "org", "net", "cn"):
            parts.append(seg)
    return parts


def _owner_matches_scene_app(pkg: str, scene_text: str) -> bool:
    """持锁包名与场景描述明显对应时，视为合理（如 Whatapp 场景 + com.whatsapp）。"""
    st = scene_text.lower()
    pkg_l = pkg.lower()
    for key, hints in APP_SCENE_ALIASES.items():
        if key in pkg_l:
            if any(h in st for h in hints):
                return True
    for part in _pkg_name_tokens(pkg_l):
        if len(part) >= 3 and part in st:
            return True
    return False


def _game_scene_owner_ok(owner_label: str, scene_text: str) -> bool:
    """游戏场景：持锁方包名与场景标题有词匹配即视为本游戏（如 Block Blast + block.juggle）。"""
    if not re.search(r"游戏|game|play", scene_text, re.I):
        return False
    pkg = extract_package(owner_label)
    st = scene_text.lower()
    for part in _pkg_name_tokens(pkg):
        if len(part) >= 3 and part in st:
            return True
    return _owner_matches_scene_app(pkg, scene_text)


def _is_phone_call_scene(scene_text: str) -> bool:
    """电话/VoIP 通话类 DOU 场景（不含纯视频播放、直播浏览）。"""
    if re.search(r"直播|\blive\b|滑动浏览|观看.*视频|播放.*视频|mxplayer|youtube|tiktok", scene_text, re.I):
        if not re.search(r"通话|dialer|phone|incall|主叫|被叫|whatsapp|whatapp|messenger|微信", scene_text, re.I):
            return False
    return bool(
        re.search(
            r"语音通话|视频通话|voice\s*call|video\s*call|"
            r"通话|dialer|incall|主叫|被叫|"
            r"whatsapp|whatapp|messenger|微信|facetime",
            scene_text,
            re.I,
        )
    )


def _owner_ok_for_call_scene(owner_label: str, scene_text: str) -> bool:
    owner_cat = classify_owner(owner_label)
    if owner_cat in ("system", "telecom"):
        return True
    pkg = extract_package(owner_label)
    if _owner_matches_scene_app(pkg, scene_text):
        return True
    st = scene_text.lower()
    if re.search(r"dialer|google dialer|phone.*通话|phone主叫|incall", st, re.I):
        return owner_cat == "telecom" or bool(
            re.search(r"dialer|incallui|telecom|phone", pkg, re.I)
        )
    if re.search(r"whatsapp|whatapp|messenger|微信|facetime", st, re.I):
        return owner_cat in ("social", "system") and _owner_matches_scene_app(
            pkg, scene_text
        )
    return False


def _is_voice_or_video_scene(scene_text: str) -> bool:
    return bool(
        re.search(
            r"语音通话|视频通话|voice\s*call|video\s*call|通话|直播|\blive\b|"
            r"whatsapp|whatapp|messenger|微信|facetime",
            scene_text,
            re.I,
        )
    )


def _dou_scripts_dir() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "scripts"


def _import_dou_utils():
    scripts = _dou_scripts_dir()
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from utils import find_test_report, is_screen_off_scene  # noqa: WPS433

    return find_test_report, is_screen_off_scene


def extract_suffix(name: object) -> str:
    m = SUFFIX_RE.search(str(name or ""))
    return m.group(1) if m else ""


def classify_scene_category(desc: str, name: str) -> str:
    _, is_screen_off_scene = _import_dou_utils()
    text = f"{desc} {name}"
    if is_screen_off_scene(desc, name):
        if _is_intentional_audio_scene(text):
            return "screen_off_music"
        return "screen_off"
    if re.search(r"主页待机|首页待机", text):
        return "idle_home"
    if re.search(
        r"dialer|google dialer|phone.*通话|phone主叫|incall|主叫通话|被叫通话",
        text,
        re.I,
    ):
        return "voice_call"
    if re.search(
        r"视频|youtube|music|音乐|播放|pip|小窗|spotify|抖音|tiktok|mxtech|videoplayer|"
        r"语音通话|视频通话|通话|call|直播|live|whatsapp|whatapp|messenger|微信",
        text,
        re.I,
    ):
        return "media"
    if re.search(r"导航|maps|google map|语音导航|导航语音|mapbox", text, re.I):
        return "maps_nav"
    if re.search(
        r"滑动|feed|浏览|instagram|facebook|twitter|reddit|pinterest|scroll",
        text,
        re.I,
    ):
        return "feed_scroll"
    if re.search(r"文档|word|excel|pdf|wps|document", text, re.I):
        return "document"
    if re.search(r"相机|拍照|gallery|图库|camera", text, re.I):
        return "camera"
    if re.search(r"下载|商店|install|应用商店|store", text, re.I):
        return "store_download"
    if re.search(r"浏览器|chrome|网页|browse|web", text, re.I):
        return "web_browse"
    if re.search(r"游戏|game|mlbb|pubg|王者|原神|mihoyo|mobile\.legends", text, re.I):
        return "game"
    return "general_on"


def extract_package(owner_label: str) -> str:
    """从 owner_label 提取包名或系统标识。"""
    text = str(owner_label or "").strip()
    m = re.search(r"\(([^)]+)\)", text)
    if m:
        return m.group(1).strip().lower()
    return text.lower()


def classify_owner(owner_label: str) -> str:
    """持锁方类型：media/maps/camera/.../other"""
    pkg = extract_package(owner_label)
    probe = f"{owner_label} {pkg}"
    for cat, pat in OWNER_CLASSIFIERS:
        if pat.search(probe):
            return cat
    return "other"


def _display_pkg(owner_label: str) -> str:
    pkg = extract_package(owner_label)
    if pkg and "." in pkg:
        return pkg.split(".")[-1] if len(pkg) > 32 else pkg
    return owner_label or "?"


def _scene_desc(sc: dict) -> str:
    return (sc.get("desc") or sc.get("name") or "该").strip()


def check_owner_scene_mismatch(
    scene_cat: str,
    scene: dict,
    owner_label: str,
    overlap_ms: int,
) -> Optional[str]:
    """场景 × 持锁方不匹配时返回原因（与是否音视频场景无关）。"""
    if overlap_ms <= 0:
        return None
    owner_cat = classify_owner(owner_label)
    pkg_disp = _display_pkg(owner_label)
    scene_name = _scene_desc(scene)
    scene_text = f"{scene_name} {scene.get('name') or ''}"
    pkg = extract_package(owner_label)

    # 包名与场景强匹配
    if _owner_matches_scene_app(pkg, scene_text):
        return None

    # 游戏场景 + 本游戏包持锁（Block Blast / MLBB 等）
    if scene_cat == "game" and (
        owner_cat == "game" or _game_scene_owner_ok(owner_label, scene_text)
    ):
        return None

    # 通话场景：仅允许对应通话/拨号应用
    if scene_cat == "voice_call" or _is_phone_call_scene(scene_text):
        if _owner_ok_for_call_scene(owner_label, scene_text):
            return None
        pkg_disp = _display_pkg(owner_label)
        return f"通话场景持锁方应为电话/拨号或系统，当前为 {pkg_disp}"

    # 场景描述与包名一致（如 TikTok 场景 + aweme 包）
    if scene_cat == "media" and owner_cat in ("media", "social", "other"):
        scene_tokens = re.findall(r"[a-zA-Z0-9]{3,}", scene_text.lower())
        pkg_tokens = re.findall(r"[a-zA-Z0-9]{3,}", pkg)
        if any(t in scene_text.lower() for t in pkg_tokens if len(t) >= 4):
            return None
        if re.search(r"tiktok|douyin|youtube|whatsapp|messenger|instagram", scene_text, re.I):
            hints = {
                "tiktok": ("aweme", "trill", "musically", "snssdk"),
                "douyin": ("aweme", "douyin"),
                "youtube": ("youtube", "vending"),
                "whatsapp": ("whatsapp",),
                "messenger": ("orca", "messenger"),
                "instagram": ("instagram",),
            }
            for key, pats in hints.items():
                if key in scene_text.lower() and any(p in pkg for p in pats):
                    return None

    for scene_cats, owner_cats, min_ms, tmpl in CROSS_DENY_RULES:
        if scene_cat in scene_cats and owner_cat in owner_cats and overlap_ms >= min_ms:
            return tmpl.format(pkg=pkg_disp, scene=scene_name)

    plausible = CATEGORY_PLAUSIBLE_OWNERS.get(scene_cat)
    if plausible is not None and owner_cat not in plausible:
        min_ms = MIN_OWNER_MISMATCH_MS
        if scene_cat in ("screen_off", "idle_home", "camera"):
            min_ms = 1_000
        if overlap_ms >= min_ms:
            allowed = "/".join(sorted(plausible))
            return (
                f"{scene_name}场景（{scene_cat}）不应由 {pkg_disp}（{owner_cat}）持锁；"
                f"合理类型：{allowed}"
            )

    return None


def _parse_scene_dt(raw: object, year: int) -> Optional[datetime]:
    if raw is None or (isinstance(raw, float) and str(raw) == "nan"):
        return None
    text = str(raw).strip()
    if not text or text.lower() == "nan":
        return None
    for fmt in (
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
    ):
        try:
            return datetime.strptime(text[:26], fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("/", "-"))
    except ValueError:
        return None


def _bug_ts_to_dt(ts: str, year: int) -> datetime:
    return datetime.strptime(f"{year}-{ts}", "%Y-%m-%d %H:%M:%S.%f")


def load_dou_scenes(high: Path, year: int) -> List[dict]:
    find_test_report, is_screen_off_scene = _import_dou_utils()
    report_path = find_test_report(str(high))
    if not report_path:
        return []
    try:
        import pandas as pd  # noqa: WPS433
    except ImportError:
        return []

    try:
        df = pd.read_excel(report_path, sheet_name="report")
    except Exception:
        return []

    required = {"name", "starttime", "endtime"}
    if not required.issubset(set(df.columns)):
        return []

    scenes: List[dict] = []
    for _, row in df.iterrows():
        name = str(row.get("name", "") or "").strip()
        desc = str(row.get("desc", "") or "").strip()
        start_dt = _parse_scene_dt(row.get("starttime"), year)
        end_dt = _parse_scene_dt(row.get("endtime"), year)
        if not name or not start_dt or not end_dt or end_dt <= start_dt:
            continue
        suffix = extract_suffix(name)
        screen_label = "灭屏" if is_screen_off_scene(desc, name) else "亮屏"
        category = classify_scene_category(desc, name)
        scenes.append(
            {
                "suffix": suffix,
                "name": name,
                "desc": desc,
                "screen_label": screen_label,
                "category": category,
                "category_label": CATEGORY_REASONS.get(category, category),
                "start": start_dt.strftime("%m-%d %H:%M:%S.%f")[:-3],
                "end": end_dt.strftime("%m-%d %H:%M:%S.%f")[:-3],
                "start_iso": start_dt.isoformat(sep=" "),
                "end_iso": end_dt.isoformat(sep=" "),
                "duration_sec": int((end_dt - start_dt).total_seconds()),
            }
        )
    scenes.sort(key=lambda s: s["start_iso"])
    return scenes


def _interval_dt_range(start: str, end: Optional[str], year: int) -> Tuple[datetime, Optional[datetime]]:
    start_dt = _bug_ts_to_dt(start, year)
    end_dt = _bug_ts_to_dt(end, year) if end else None
    return start_dt, end_dt


def _union_overlap_ranges_ms(ranges: List[Tuple[datetime, datetime]]) -> int:
    """Merge overlapping windows and return total span in ms."""
    if not ranges:
        return 0
    merged: List[Tuple[datetime, datetime]] = []
    for w0, w1 in sorted(ranges, key=lambda x: x[0]):
        if merged and w0 <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], w1))
        else:
            merged.append((w0, w1))
    total = 0
    for w0, w1 in merged:
        total += max(0, int((w1 - w0).total_seconds() * 1000))
    return total


def _overlap_window(
    i0: datetime, i1: datetime, s0: datetime, s1: datetime
) -> Tuple[datetime, datetime]:
    return max(i0, s0), min(i1, s1)


def _scene_overlap_entry(
    sc: dict,
    cat: str,
    ov_ms: int,
    w0: datetime,
    w1: datetime,
    *,
    owner_pkg: str,
    owner_cat: str,
    is_abnormal: bool = False,
    reason: str = "",
    anomaly_kind: str = "",
    threshold_ms: Optional[int] = None,
    threshold_txt: str = "",
    owner_matched: bool = False,
) -> dict:
    ov_txt = _format_ms(ov_ms)
    return {
        "suffix": sc["suffix"],
        "name": sc["name"],
        "desc": sc["desc"],
        "screen_label": sc["screen_label"],
        "category": cat,
        "overlap_ms": ov_ms,
        "overlap_text": ov_txt,
        "overlap_start_iso": w0.isoformat(),
        "overlap_end_iso": w1.isoformat(),
        "threshold_ms": threshold_ms,
        "threshold_text": threshold_txt,
        "anomaly_kind": anomaly_kind,
        "abnormal": is_abnormal,
        "reason": reason,
        "owner_pkg": owner_pkg,
        "owner_category": owner_cat,
        "owner_matched": owner_matched,
    }


def _overlap_ms(a0: datetime, a1: datetime, b0: datetime, b1: datetime) -> int:
    lo = max(a0, b0)
    hi = min(a1, b1)
    if hi <= lo:
        return 0
    return int((hi - lo).total_seconds() * 1000)


def scenes_at_time(scenes: List[dict], ts: str, year: int) -> List[dict]:
    dt = _bug_ts_to_dt(ts, year)
    hits = []
    for sc in scenes:
        s0 = datetime.fromisoformat(sc["start_iso"])
        s1 = datetime.fromisoformat(sc["end_iso"])
        if s0 <= dt < s1:
            hits.append(
                {
                    "suffix": sc["suffix"],
                    "name": sc["name"],
                    "desc": sc["desc"],
                    "screen_label": sc["screen_label"],
                    "category": sc["category"],
                }
            )
    return hits


def annotate_interval(
    interval: Any,
    scenes: List[dict],
    year: int,
) -> Tuple[List[dict], bool, List[str]]:
    if interval.incomplete or not interval.end:
        return [], False, []
    if getattr(interval, "unreliable", False):
        return [], False, []

    i0, i1 = _interval_dt_range(interval.start, interval.end, year)
    if not i1:
        return [], False, []

    overlapping: List[dict] = []
    reasons: List[str] = []
    abnormal = False
    owner_cat = classify_owner(interval.owner_label)
    owner_pkg = extract_package(interval.owner_label)

    for sc in scenes:
        s0 = datetime.fromisoformat(sc["start_iso"])
        s1 = datetime.fromisoformat(sc["end_iso"])
        ov_ms = _overlap_ms(i0, i1, s0, s1)
        if ov_ms <= 0:
            continue
        w0, w1 = _overlap_window(i0, i1, s0, s1)
        cat = sc["category"]
        threshold = CATEGORY_THRESHOLDS_MS.get(cat, CATEGORY_THRESHOLDS_MS["general_on"])
        is_abnormal = False
        reason = ""

        # 包名与场景匹配 → 本段持锁正常，不做后续判定
        if _owner_belongs_to_scene(interval.owner_label, sc):
            overlapping.append(
                _scene_overlap_entry(
                    sc,
                    cat,
                    ov_ms,
                    w0,
                    w1,
                    owner_pkg=owner_pkg,
                    owner_cat=owner_cat,
                    owner_matched=True,
                )
            )
            continue

        ov_txt = _format_ms(ov_ms)
        mismatch = check_owner_scene_mismatch(cat, sc, interval.owner_label, ov_ms)
        anomaly_kind = ""
        threshold_ms: Optional[int] = None
        threshold_txt = ""
        if mismatch:
            is_abnormal = True
            anomaly_kind = "owner_mismatch"
            reason = f"{mismatch}（异常持锁 {ov_txt}）"
            abnormal = True
            if reason not in reasons:
                reasons.append(reason)
        elif interval.kind == "longwake" and threshold is not None and ov_ms >= threshold:
            is_abnormal = True
            anomaly_kind = "duration"
            threshold_ms = threshold
            threshold_txt = _format_ms(threshold)
            base = CATEGORY_REASONS.get(cat, "该场景不应长时间 AudioMix 持锁")
            reason = f"{base}（异常持锁 {ov_txt} ≥ 阈值 {threshold_txt}）"
            abnormal = True
            if reason not in reasons:
                reasons.append(reason)

        overlapping.append(
            _scene_overlap_entry(
                sc,
                cat,
                ov_ms,
                w0,
                w1,
                owner_pkg=owner_pkg,
                owner_cat=owner_cat,
                is_abnormal=is_abnormal,
                reason=reason,
                anomaly_kind=anomaly_kind,
                threshold_ms=threshold_ms,
                threshold_txt=threshold_txt,
            )
        )

    # 任一重叠场景异常 → 整段持锁异常（不因主场景匹配而抹掉其他场景异常）
    abnormal = any(o.get("abnormal") for o in overlapping)
    reasons = []
    for o in overlapping:
        r = o.get("reason") or ""
        if r and r not in reasons:
            reasons.append(r)

    return overlapping, abnormal, reasons


def _abnormal_duration_meta(sc_list: List[dict]) -> dict:
    """Summarize abnormal hold time as union of abnormal scene overlaps."""
    ab_scenes = [s for s in sc_list if s.get("abnormal")]
    if not ab_scenes:
        return {}
    ranges: List[Tuple[datetime, datetime]] = []
    for s in ab_scenes:
        s0 = s.get("overlap_start_iso")
        s1 = s.get("overlap_end_iso")
        if s0 and s1:
            ranges.append((datetime.fromisoformat(s0), datetime.fromisoformat(s1)))
    union_ms = _union_overlap_ranges_ms(ranges)
    if union_ms <= 0:
        union_ms = max(s.get("overlap_ms") or 0 for s in ab_scenes)
    primary = max(ab_scenes, key=lambda x: x.get("overlap_ms") or 0)
    annotations: List[dict] = []
    for s in ab_scenes:
        item = {
            "scene": s.get("desc") or s.get("name") or "",
            "suffix": s.get("suffix") or "",
            "overlap_ms": s.get("overlap_ms") or 0,
            "overlap_text": s.get("overlap_text") or _format_ms(s.get("overlap_ms") or 0),
            "anomaly_kind": s.get("anomaly_kind") or "",
            "reason": s.get("reason") or "",
        }
        if s.get("threshold_text"):
            item["threshold_ms"] = s.get("threshold_ms")
            item["threshold_text"] = s.get("threshold_text")
        annotations.append(item)
    union_txt = _format_ms(union_ms)
    max_scene_ms = primary.get("overlap_ms") or 0
    return {
        "abnormal_hold_ms": union_ms,
        "abnormal_hold_text": union_txt,
        "overlap_ms": union_ms,
        "overlap_text": union_txt,
        "max_scene_overlap_ms": max_scene_ms,
        "max_scene_overlap_text": primary.get("overlap_text") or _format_ms(max_scene_ms),
        "threshold_ms": primary.get("threshold_ms"),
        "threshold_text": primary.get("threshold_text") or "",
        "anomaly_kind": primary.get("anomaly_kind") or "",
        "duration_annotations": annotations,
    }


def annotate_report(report: Any, high: Path) -> Any:
    """Enrich AudioMixReport with DOU scene alignment."""
    year = int(report.timeline_events[0].dt[:4]) if report.timeline_events else datetime.now().year
    scenes = load_dou_scenes(high, year)
    report.scenes = scenes

    abnormal_intervals: List[dict] = []
    for itv in report.intervals:
        sc_list, is_ab, reasons = annotate_interval(itv, scenes, year)
        itv.scenes = sc_list
        itv.abnormal = is_ab
        itv.abnormal_reasons = reasons
        if is_ab:
            meta = _abnormal_duration_meta(sc_list)
            itv.abnormal_hold_ms = meta.get("abnormal_hold_ms", 0)
            itv.abnormal_hold_text = meta.get("abnormal_hold_text", "")
        if is_ab and not itv.incomplete:
            meta = _abnormal_duration_meta(sc_list)
            abnormal_intervals.append(
                {
                    "start": itv.start,
                    "end": itv.end,
                    "owner_label": itv.owner_label,
                    "owner_pkg": extract_package(itv.owner_label),
                    "owner_category": classify_owner(itv.owner_label),
                    "duration_text": itv.duration_text,
                    "bucket": itv.bucket,
                    "scenes": sc_list,
                    "reasons": reasons,
                    **meta,
                }
            )

    for ev in report.timeline_events:
        ev.scenes_at = scenes_at_time(scenes, ev.timestamp, year)

    report.abnormal_intervals = abnormal_intervals
    report.abnormal_count = len(abnormal_intervals)
    return report
