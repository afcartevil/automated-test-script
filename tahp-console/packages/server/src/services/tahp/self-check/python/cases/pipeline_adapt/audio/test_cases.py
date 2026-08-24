"""pipeline_adapt / 音频用例列表（由 case1 顺序编排执行）。"""

from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from typing import Any

from _common import (
    StepFn,
    adb_cat,
    adb_run,
    adb_shell,
    emit,
    get_screen_size,
    input_swipe,
    try_adb_root,
)
from utils.tdd.ui_automatic import ensure_screen_on_and_unlocked
from utils.tdd.ui_u2 import dump_hierarchy_xml, release_uiautomator2
from utils.tdd.ui_xml import node_reported_displayed, parse_bounds_center

# --- 录音机 ---
_PACKAGE = "com.transsion.soundrecorder"
_ACTIVITY = "com.transsion.soundrecorder.SoundRecorder"
_COMPONENT = f"{_PACKAGE}/{_ACTIVITY}"
_RECORD_BTN_RID = "com.transsion.soundrecorder:id/btn_record_container"
_WAVEFORM_RID = "com.transsion.soundrecorder:id/record_frame_view"

_GRANT_PERMS = (
    "android.permission.RECORD_AUDIO",
    "android.permission.POST_NOTIFICATIONS",
    "android.permission.READ_MEDIA_AUDIO",
    "android.permission.READ_EXTERNAL_STORAGE",
    "android.permission.WRITE_EXTERNAL_STORAGE",
)

_PERMISSION_RIDS = (
    "com.android.permissioncontroller:id/permission_allow_foreground_only_button",
    "com.android.permissioncontroller:id/permission_allow_button",
    "com.android.permissioncontroller:id/permission_allow_one_time_button",
    "com.android.packageinstaller:id/permission_allow_button",
    "android:id/button1",
)

_DIALOG_TEXTS = (
    "允许",
    "Allow",
    "仅在使用该应用时允许",
    "While using the app",
    "同意",
    "Agree",
    "开始使用",
)

# --- 参数路径 / DTS / ADSP ---
_AUDIO_DIR = "/odm/etc/vconfig/audio"
_EXPECT_PARAM_DIR = "/odm/etc/vconfig/audio/audio_param"
_EXPECT_PARAM_PATH = f'param_path="{_EXPECT_PARAM_DIR}"'
_PARAM_VAL_RE = re.compile(
    r"""param_path\s*=\s*["']([^"']+)["']|<param_path>\s*([^<]+)\s*</param_path>""",
    re.I,
)
_DTS_CFG = "/odm/etc/asset/audio/dts/customer.cfg"
_EXPECT_TUNING_PATH = "tuningPath=/odm/etc/asset/audio/dts"
_DSP_DT = "/proc/device-tree/snd-audio-dsp"
_ADSP_STATE = "/sys/kernel/debug/pm_genpd/adsp_top_dormant/current_state"
_EXPECT_ADSP_ON = "onn-1"
_TUNING_RE = re.compile(r"tuningPath\s*=\s*(\S+)", re.I)

# --- PA ---
_CONF_PATH = "/odm/etc/vconfig/audio/TranAudioConfiguration.conf"
_FSM_MACROS = ("TRAN_AUDIO_FS1599N_SUPPORT", "TRAN_AUDIO_FS1589N_SUPPORT")
_AW_OCA_MACROS = ("TRAN_AUDIO_AW87XXX_SUPPORT", "TRAN_AUDIO_OCA72XXX_SUPPORT")
_EXPECT = {
    "fsm": {
        "media": "scene:0001",
        "notification": "scene:0001",
        "ring": "scene:0008",
        "alarm": "scene:0008",
        "handset": "scene:8000",
        "speaker": "scene:0002",
    },
    "aw_oca": {
        "media": "Music",
        "notification": "Music",
        "ring": "Ring",
        "alarm": "Ring",
        "handset": "Receiver",
        "speaker": "Voice",
    },
}
_VOLUME_BARS = (
    ("媒体", ("媒体", "Media")),
    ("通知", ("通知", "Notifications")),
    ("铃声", ("铃声", "Ring volume")),
    ("闹钟", ("闹钟", "Alarm")),
)
_VOLUME_KEYS = {
    "媒体": "media",
    "通知": "notification",
    "铃声": "ring",
    "闹钟": "alarm",
}
_SPEAKER_DESCS = (
    "扬声器",
    "免提",
    "Speaker",
    "speaker",
    "Audio",
    "音频",
)
_SPEAKER_RID_FRAGS = (
    "speaker",
    "audio_button",
    "audioButton",
    "audio_route",
    "toggle_speaker",
)
_MACRO_YES_RE = re.compile(
    r"(?:^|\n)\s*(?:#\s*define\s+)?(TRAN_AUDIO_(?:FS1599N|FS1589N|AW87XXX|OCA72XXX)_SUPPORT)"
    r"\s*[=: \t]+(yes|1|true)\b",
    re.I,
)
_SCENE_RE = re.compile(r"scene\s*[=:]\s*(\d+)", re.I)
_AW_PROFILE_RE = re.compile(r"(?:aw_)?profile\s*[=:]\s*(\w+)", re.I)

_STATUS_SUFFIX = {
    "pass": "成功",
    "fail": "失败",
    "skip": "跳过",
}


def _item(name: str, status: str, message: str) -> dict[str, Any]:
    return {"name": name, "status": status, "message": message}


def _parse_bounds(bounds: str) -> tuple[int, int, int, int] | None:
    parts = (bounds or "").replace("][", ",").replace("[", "").replace("]", "").split(",")
    if len(parts) != 4:
        return None
    try:
        x1, y1, x2, y2 = (int(v) for v in parts)
    except ValueError:
        return None
    return x1, y1, x2, y2


def _dump_xml(serial: str) -> str:
    return dump_hierarchy_xml(serial) or ""


def _call_offhook(serial: str) -> bool:
    text = adb_shell(serial, "dumpsys telephony.registry 2>/dev/null | grep mCallState", timeout=15)
    return "=1" in (text or "") or "=2" in (text or "")


def _end_call(serial: str) -> None:
    adb_run(serial, "shell", "input", "keyevent", "KEYCODE_ENDCALL", timeout=8)
    time.sleep(0.3)
    adb_run(serial, "shell", "input", "keyevent", "KEYCODE_ENDCALL", timeout=8)


def _start_call_10086(serial: str) -> bool:
    ret = adb_run(
        serial,
        "shell",
        "am",
        "start",
        "-a",
        "android.intent.action.CALL",
        "-d",
        "tel:10086",
        timeout=15,
    )
    out = f"{ret.stdout or ''}{ret.stderr or ''}"
    return ret.returncode == 0 and "Error" not in out and "Exception" not in out


def _ls_names(serial: str, directory: str) -> list[str]:
    out = adb_shell(serial, f"ls -1 {directory} 2>/dev/null")
    if not out or "no such file" in out.lower():
        return []
    return [name.strip() for name in out.split() if name.strip()]


def test_audio_param_path(
    serial: str,
    *,
    steps: list[str],
    step_update: StepFn | None = None,
    **_,
) -> dict[str, Any]:
    """
    音频参数路径是否正确检查
    测试步骤: 读取 /odm/etc/vconfig/audio/aurisys_config*.xml 中含 audio_param 的行
    预期结果: 均为 param_path="/odm/etc/vconfig/audio/audio_param"
    """
    name = "音频参数路径检查"
    emit(step_update, steps, f"[参数路径] 列出 {_AUDIO_DIR}/aurisys_config*.xml")
    files = [
        f"{_AUDIO_DIR}/{n}"
        for n in _ls_names(serial, _AUDIO_DIR)
        if n.lower().startswith("aurisys_config") and n.lower().endswith(".xml")
    ]
    if not files:
        emit(step_update, steps, f"[{name}]-失败")
        return _item(name, "fail", f"未找到 {_AUDIO_DIR}/aurisys_config*.xml")

    hits: list[str] = []
    bad: list[str] = []
    for path in files:
        text = adb_cat(serial, path)
        emit(step_update, steps, f"[参数路径] 读取 {path}")
        matched = False
        for raw in (text or "").splitlines():
            line = raw.strip()
            if "audio_param" not in line.lower():
                continue
            matched = True
            hits.append(f"{path}: {line}")
            parsed = _PARAM_VAL_RE.search(line)
            value = ""
            if parsed:
                value = (parsed.group(1) or parsed.group(2) or "").strip().rstrip("/")
            # 必须整段相等：/odm/etc/vconfig/audio 是 /audio_param 的前缀，不能用 in 判断
            ok = value == _EXPECT_PARAM_DIR
            if not ok:
                bad.append(f"{path}: {line}")
        if not matched:
            emit(step_update, steps, f"[参数路径] {path} 无 audio_param 行")

    if not hits:
        emit(step_update, steps, f"[{name}]-失败")
        return _item(name, "fail", "aurisys_config*.xml 中未找到 audio_param")
    preview = " | ".join(hits[:8])
    emit(step_update, steps, f"[参数路径] 命中: {preview}")
    if bad:
        emit(step_update, steps, f"[{name}]-失败")
        return _item(
            name,
            "fail",
            f"存在非 {_EXPECT_PARAM_PATH} 的 audio_param: {'; '.join(bad[:4])}",
        )
    emit(step_update, steps, f"[{name}]-成功")
    return _item(name, "pass", f"共 {len(hits)} 处均为 {_EXPECT_PARAM_PATH}")


def test_dts_tuning_path(
    serial: str,
    *,
    steps: list[str],
    step_update: StepFn | None = None,
    **_,
) -> dict[str, Any]:
    """
    dts音效参数路径检查
    测试步骤: cat /odm/etc/asset/audio/dts/customer.cfg 中 tuningPath
    预期结果: tuningPath=/odm/etc/asset/audio/dts
    """
    name = "dts音效参数路径检查"
    emit(step_update, steps, f"[DTS] 检查 {_DTS_CFG}")
    if "存在" not in adb_shell(serial, f"[ -f {_DTS_CFG} ] && echo 存在"):
        emit(step_update, steps, f"[DTS] 文件不存在，跳过: {_DTS_CFG}")
        return _item(name, "skip", f"未找到 {_DTS_CFG}，跳过 DTS 路径检查")
    text = adb_cat(serial, _DTS_CFG)

    lines = [ln.strip() for ln in text.splitlines() if "tuningpath" in ln.lower()]
    preview = " | ".join(lines[:6]) or "<空>"
    emit(step_update, steps, f"[DTS] 输出: {preview}")
    if not lines:
        emit(step_update, steps, f"[{name}]-失败")
        return _item(name, "fail", f"{_DTS_CFG} 中未找到 tuningPath")

    values: list[str] = []
    for line in lines:
        match = _TUNING_RE.search(line.replace('"', "").replace("'", ""))
        if match:
            values.append(match.group(1).rstrip("/"))
        elif _EXPECT_TUNING_PATH.lower() in line.lower().replace(" ", "").replace('"', ""):
            values.append(_EXPECT_TUNING_PATH.split("=", 1)[1])

    expect_val = _EXPECT_TUNING_PATH.split("=", 1)[1]
    if any(v == expect_val for v in values) and all(v == expect_val for v in values):
        emit(step_update, steps, f"[{name}]-成功")
        return _item(name, "pass", _EXPECT_TUNING_PATH)
    emit(step_update, steps, f"[{name}]-失败")
    return _item(
        name,
        "fail",
        f"expected {_EXPECT_TUNING_PATH}; actual: {preview}",
    )


def _rid_matches(node_rid: str, target: str) -> bool:
    rid = (node_rid or "").strip()
    needle = (target or "").strip()
    if not rid or not needle:
        return False
    if rid == needle:
        return True
    suffix = needle.split("/")[-1]
    return rid.endswith(f"/{suffix}") or rid.endswith(f":id/{suffix}")


def _node_size_ok(el: ET.Element, *, min_w: int = 8, min_h: int = 8) -> bool:
    if not node_reported_displayed(el):
        return False
    box = _parse_bounds(el.attrib.get("bounds") or "")
    if not box:
        return False
    x1, y1, x2, y2 = box
    return (x2 - x1) >= min_w and (y2 - y1) >= min_h


def _find_nodes(xml: str, rid: str) -> list[ET.Element]:
    if not xml:
        return []
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return []
    return [el for el in root.iter("node") if _rid_matches(el.attrib.get("resource-id") or "", rid)]


def _tap_xy(serial: str, x: int, y: int) -> bool:
    ret = adb_run(serial, "shell", "input", "tap", str(x), str(y))
    return ret.returncode == 0


def _tap_rid(serial: str, xml: str, rid: str) -> bool:
    for el in _find_nodes(xml, rid):
        if not _node_size_ok(el):
            continue
        try:
            cx, cy = parse_bounds_center(el.attrib.get("bounds") or "")
        except ValueError:
            continue
        if _tap_xy(serial, cx, cy):
            time.sleep(0.45)
            return True
    return False


def _tap_texts(serial: str, xml: str, texts: tuple[str, ...]) -> bool:
    if not xml:
        return False
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return False
    wanted = {t.strip() for t in texts if t.strip()}
    for el in root.iter("node"):
        label = (el.attrib.get("text") or "").strip() or (el.attrib.get("content-desc") or "").strip()
        if label not in wanted:
            continue
        if not _node_size_ok(el):
            continue
        try:
            cx, cy = parse_bounds_center(el.attrib.get("bounds") or "")
        except ValueError:
            continue
        if _tap_xy(serial, cx, cy):
            time.sleep(0.4)
            return True
    return False


def _dismiss_blocking_dialogs(serial: str, xml: str) -> bool:
    for rid in _PERMISSION_RIDS:
        if _tap_rid(serial, xml, rid):
            return True
    return _tap_texts(serial, xml, _DIALOG_TEXTS)


def _pkg_installed(serial: str) -> bool:
    out = adb_shell(serial, f"pm path {_PACKAGE}", timeout=15)
    return "package:" in (out or "").lower()


def _grant_recorder_permissions(serial: str) -> None:
    for perm in _GRANT_PERMS:
        adb_run(serial, "shell", "pm", "grant", _PACKAGE, perm, timeout=10)
    adb_shell(serial, f"appops set {_PACKAGE} RECORD_AUDIO allow")
    adb_shell(serial, f"appops set {_PACKAGE} RECORD_AUDIO 0")


def _force_stop(serial: str) -> None:
    adb_run(serial, "shell", "am", "force-stop", _PACKAGE, timeout=10)
    time.sleep(0.3)


def _open_recorder(serial: str) -> tuple[bool, str]:
    _force_stop(serial)
    ret = adb_run(serial, "shell", "am", "start", "-n", _COMPONENT, timeout=15)
    out = f"{ret.stdout or ''}{ret.stderr or ''}"
    if ret.returncode == 0 and "Error" not in out and "Exception" not in out:
        time.sleep(1.2)
        return True, ""
    monkey = adb_run(
        serial,
        "shell",
        "monkey",
        "-p",
        _PACKAGE,
        "-c",
        "android.intent.category.LAUNCHER",
        "1",
        timeout=20,
    )
    if monkey.returncode == 0:
        time.sleep(1.2)
        return True, ""
    return False, out.strip() or "am start / monkey 启动失败"


def _visible_rid(xml: str, rid: str, *, min_h: int = 8) -> ET.Element | None:
    for el in _find_nodes(xml, rid):
        if _node_size_ok(el, min_h=min_h):
            return el
    return None


def _audio_capture_active(serial: str) -> bool:
    """dumpsys 中出现录音机包名且邻近 record，作为麦克风采集（振幅来源）旁证。"""
    pkg = _PACKAGE.lower()
    audio = adb_shell(serial, f"dumpsys audio 2>/dev/null | grep -i {pkg}", timeout=5)
    low = (audio or "").lower()
    if pkg in low and ("record" in low or "source" in low or "in=" in low):
        return True
    flinger = adb_shell(serial, f"dumpsys media.audio_flinger 2>/dev/null | grep -i {pkg}", timeout=5)
    return bool((flinger or "").strip())


def _wait_record_button(
    serial: str,
    *,
    steps: list[str],
    step_update: StepFn | None,
    timeout: float = 18.0,
) -> tuple[str, str]:
    deadline = time.time() + timeout
    last_xml = ""
    while time.time() < deadline:
        xml = _dump_xml(serial)
        last_xml = xml
        if _dismiss_blocking_dialogs(serial, xml):
            emit(step_update, steps, "[录音机] 已点击权限/协议弹窗")
            time.sleep(0.6)
            continue
        if _visible_rid(xml, _RECORD_BTN_RID):
            return xml, ""
        time.sleep(0.6)
    return last_xml, "未找到录音按钮 btn_record_container"


def test_recording_function(
    serial: str,
    *,
    steps: list[str],
    step_update: StepFn | None = None,
    **_,
) -> dict[str, Any]:
    """
    录音功能检查
    测试步骤:
    1. 打开录音机应用，进入主界面，底部显示红色圆形录音按钮
    2. 点击红色圆形录音按钮开始录音
    3. 观察录音界面，确认是否显示录音波形动画
    4. 点击暂停按钮停止录音
    预期结果: 第三步中录音界面出现波形动画（波形有振幅）
    """
    name = "录音功能检查"
    try:
        emit(step_update, steps, "[录音机] 亮屏解锁")
        if not ensure_screen_on_and_unlocked(serial):
            emit(step_update, steps, "[录音机] 亮屏解锁-失败")
            return _item(name, "fail", "亮屏解锁失败")
        emit(step_update, steps, "[录音机] 亮屏解锁-成功")

        emit(step_update, steps, f"[录音机] 检查已安装 {_PACKAGE}")
        if not _pkg_installed(serial):
            emit(step_update, steps, "[录音机]-失败")
            return _item(name, "fail", f"未安装录音机应用 {_PACKAGE}")
        emit(step_update, steps, "[录音机] 应用已安装")

        emit(step_update, steps, "[录音机] 授予麦克风等运行时权限")
        _grant_recorder_permissions(serial)

        emit(step_update, steps, f"[录音机] 打开 {_COMPONENT}")
        ok, err = _open_recorder(serial)
        if not ok:
            emit(step_update, steps, "[录音机] 打开应用-失败")
            return _item(name, "fail", f"打开录音机失败: {err}")
        emit(step_update, steps, "[录音机] 打开应用-成功")

        emit(step_update, steps, "[录音机] 等待主界面录音按钮")
        xml, wait_err = _wait_record_button(serial, steps=steps, step_update=step_update)
        if wait_err:
            emit(step_update, steps, f"[录音机] {wait_err}")
            emit(step_update, steps, "[录音机]-失败")
            return _item(name, "fail", wait_err)
        emit(step_update, steps, "[录音机] 主界面录音按钮-成功")

        idle_wave = _visible_rid(xml, _WAVEFORM_RID, min_h=40)
        emit(step_update, steps, "[录音机] 点击红色圆形录音按钮开始录音")
        if not _tap_rid(serial, xml, _RECORD_BTN_RID):
            emit(step_update, steps, "[录音机] 点击录音按钮-失败")
            return _item(name, "fail", "点击录音按钮失败")
        time.sleep(1.2)

        xml = _dump_xml(serial)
        if _dismiss_blocking_dialogs(serial, xml):
            emit(step_update, steps, "[录音机] 录音后出现权限弹窗，已允许")
            time.sleep(0.8)
            xml = _dump_xml(serial)
            if not _visible_rid(xml, _WAVEFORM_RID, min_h=40):
                _tap_rid(serial, xml, _RECORD_BTN_RID)
                time.sleep(1.2)

        emit(step_update, steps, "[录音机] 检查录音波形控件 record_frame_view")
        wave_el: ET.Element | None = None
        deadline = time.time() + 8.0
        while time.time() < deadline:
            xml = _dump_xml(serial)
            _dismiss_blocking_dialogs(serial, xml)
            wave_el = _visible_rid(xml, _WAVEFORM_RID, min_h=40)
            if wave_el is not None:
                break
            time.sleep(0.5)

        if wave_el is None:
            emit(step_update, steps, "[录音机] 波形控件-失败")
            emit(step_update, steps, f"[{name}]-失败")
            return _item(name, "fail", "录音界面未出现波形控件 record_frame_view")

        box = _parse_bounds(wave_el.attrib.get("bounds") or "") or (0, 0, 0, 0)
        emit(
            step_update,
            steps,
            f"[录音机] 波形控件可见 bounds={box}（相对开始前: {'已存在' if idle_wave is not None else '新出现'}）",
        )

        capturing = False
        if idle_wave is not None:
            emit(step_update, steps, "[录音机] 检查麦克风采集（波形振幅旁证）")
            capturing = _audio_capture_active(serial)
            emit(
                step_update,
                steps,
                f"[录音机] dumpsys 录音采集: {'有' if capturing else '未检出'}",
            )
            if not capturing:
                emit(step_update, steps, "[录音机] 波形在开始前已存在且未检出采集，无法确认振幅")
                emit(step_update, steps, f"[{name}]-失败")
                return _item(name, "fail", "波形控件在开始录音前已存在，且未检测到麦克风采集，无法确认波形有振幅")

        emit(step_update, steps, "[录音机] 点击暂停/结束按钮停止录音")
        xml = _dump_xml(serial)
        if not _tap_rid(serial, xml, _RECORD_BTN_RID):
            emit(step_update, steps, "[录音机] 停止录音点击未命中，将 force-stop 清理")
        else:
            emit(step_update, steps, "[录音机] 停止录音-成功")

        amp_hint = "且 dumpsys 检出麦克风采集" if capturing else "波形控件在开始录音后出现"
        emit(step_update, steps, f"[{name}]-成功")
        return _item(name, "pass", f"录音界面出现波形动画（波形有振幅，{amp_hint}）")
    finally:
        _force_stop(serial)
        adb_run(serial, "shell", "input", "keyevent", "3", timeout=8)


def _macro_enabled(conf: str, key: str) -> bool:
    for match in _MACRO_YES_RE.finditer(conf or ""):
        if match.group(1).upper() == key.upper():
            return True
    pat = re.compile(rf"{re.escape(key)}\s*[=: \t]+(\S+)", re.I)
    for match in pat.finditer(conf or ""):
        val = match.group(1).strip().strip("\"'").lower()
        if val in {"yes", "1", "true"}:
            return True
        if val in {"no", "0", "false"}:
            return False
    return False


def detect_pa_kind(conf: str) -> tuple[str, str]:
    """返回 (fsm|aw_oca|unknown, 说明)。"""
    fsm_hit = [k for k in _FSM_MACROS if _macro_enabled(conf, k)]
    aw_hit = [k for k in _AW_OCA_MACROS if _macro_enabled(conf, k)]
    if fsm_hit and not aw_hit:
        return "fsm", ",".join(f"{k}=yes" for k in fsm_hit)
    if aw_hit and not fsm_hit:
        return "aw_oca", ",".join(f"{k}=yes" for k in aw_hit)
    if fsm_hit and aw_hit:
        return "unknown", f"同时命中 fsm={fsm_hit} aw/oca={aw_hit}"
    return "unknown", "未命中 FS1599N/FS1589N/AW87XXX/OCA72XXX=yes"


def _scene_want(token: str) -> int | None:
    low = (token or "").lower()
    if not (low.startswith("scene=") or low.startswith("scene:")):
        return None
    return int(re.split(r"[=:]", token, maxsplit=1)[1], 10)


def _fsm_on_lines(text: str) -> str:
    lines: list[str] = []
    for ln in (text or "").splitlines():
        low = ln.lower()
        if "fsm_speaker_on" in low and "fsm_speaker_off" not in low:
            lines.append(ln)
    return "\n".join(lines)


def _token_hit(text: str, token: str, *, kind: str = "") -> bool:
    raw = _fsm_on_lines(text) if kind == "fsm" else (text or "")
    want = _scene_want(token)
    if want is not None:
        return any(int(m.group(1), 10) == want for m in _SCENE_RE.finditer(raw))
    name = token.split("=", 1)[1] if token.lower().startswith("profile=") else token
    return (
        re.search(
            rf"(?:aw_)?profile\s*[=:]\s*{re.escape(name)}\b|\b{re.escape(name)}\b",
            raw,
            re.I,
        )
        is not None
    )


def _format_hits(kind: str, log: str) -> str:
    raw = _fsm_on_lines(log) if kind == "fsm" else (log or "")
    if kind == "fsm":
        scenes = []
        for m in _SCENE_RE.finditer(raw):
            tag = f"scene:{int(m.group(1), 10):04d}"
            if tag not in scenes:
                scenes.append(tag)
        return ",".join(scenes)
    names: list[str] = []
    for m in _AW_PROFILE_RE.finditer(raw):
        name = m.group(1)
        if name not in names:
            names.append(name)
    if names:
        return ",".join(names)
    return ""


def _dmesg_clear(serial: str) -> tuple[bool, str]:
    ret = adb_run(serial, "shell", "dmesg", "-C", timeout=15)
    out = f"{ret.stdout or ''}{ret.stderr or ''}"
    low = out.lower()
    if "permission denied" in low or "operation not permitted" in low:
        return False, out.strip() or "dmesg -C permission denied"
    if "unknown option" in low or "invalid option" in low:
        ret = adb_run(serial, "shell", "dmesg", "-c", timeout=15)
        out = f"{ret.stdout or ''}{ret.stderr or ''}"
        low = out.lower()
        if "permission denied" in low or "operation not permitted" in low:
            return False, out.strip() or "dmesg -c permission denied"
    return True, out.strip()


def _dmesg_raw(serial: str) -> str:
    """整段 dmesg，不在设备上管道 grep（Windows/adb 常把 | 当参数，结果读空）。"""
    ret = adb_run(serial, "shell", "dmesg", timeout=15)
    return ((ret.stdout or "") or (ret.stderr or "")).strip()


def _dmesg_pa(serial: str, kind: str) -> str:
    raw = _dmesg_raw(serial)
    if kind == "fsm":
        return _fsm_on_lines(raw)
    return "\n".join(
        ln
        for ln in (raw or "").splitlines()
        if "aw_profile" in ln.lower() or "set_aw" in ln.lower()
    )


def _read_conf(serial: str) -> tuple[str, str]:
    text = adb_cat(serial, _CONF_PATH, timeout=15)
    if text and "No such file" not in text:
        return _CONF_PATH, text
    return _CONF_PATH, ""


def _open_sound_settings(serial: str) -> tuple[bool, str]:
    adb_run(serial, "shell", "am", "force-stop", "com.android.settings", timeout=10)
    time.sleep(0.25)
    ret = adb_run(serial, "shell", "am", "start", "-a", "android.settings.SOUND_SETTINGS", timeout=15)
    out = f"{ret.stdout or ''}{ret.stderr or ''}"
    if ret.returncode == 0 and "Error" not in out and "Exception" not in out:
        time.sleep(0.7)
        return True, ""
    return False, out.strip() or "SOUND_SETTINGS 启动失败"


def _swipe_screen_up(serial: str) -> bool:
    size = get_screen_size(serial)
    if not size:
        return False
    w, h = size
    return input_swipe(serial, w // 2, int(h * 0.72), w // 2, int(h * 0.32), 380)


def _rid_name(el: ET.Element) -> str:
    return (el.attrib.get("resource-id") or "").rsplit("/", 1)[-1]


def _is_volume_seekbar(el: ET.Element) -> bool:
    """传音声音页进度条是 View + tran_seekbar，不是标准 SeekBar。"""
    rid = (el.attrib.get("resource-id") or "").lower()
    if "seekbar" in rid:
        return True
    cls = el.attrib.get("class") or ""
    return "SeekBar" in cls or "Slider" in cls


def _bar_width(el: ET.Element) -> int:
    box = _parse_bounds(el.attrib.get("bounds") or "")
    if not box:
        return 0
    return box[2] - box[0]


def _exact_desc_or_text(el: ET.Element, needles: tuple[str, ...]) -> bool:
    desc = (el.attrib.get("content-desc") or "").strip()
    text = (el.attrib.get("text") or "").strip()
    return desc in needles or text in needles


def _best_slider_for_descs(xml: str, descs: tuple[str, ...]) -> ET.Element | None:
    if not xml:
        return None
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return None
    nodes = [el for el in root.iter("node") if _node_size_ok(el)]
    matched_bars = [
        el for el in nodes if _is_volume_seekbar(el) and _exact_desc_or_text(el, descs)
    ]
    if matched_bars:
        return max(matched_bars, key=_bar_width)

    titles = [el for el in nodes if _rid_name(el) == "title" and _exact_desc_or_text(el, descs)]
    bars = [el for el in nodes if _is_volume_seekbar(el)]
    best: ET.Element | None = None
    best_gap = 10**9
    for title in titles:
        tb = _parse_bounds(title.attrib.get("bounds") or "")
        if not tb:
            continue
        for bar in bars:
            bb = _parse_bounds(bar.attrib.get("bounds") or "")
            if not bb:
                continue
            gap = bb[1] - tb[3]
            if -16 <= gap <= 240 and gap < best_gap:
                best, best_gap = bar, gap
    return best


def _swipe_seekbar(serial: str, el: ET.Element) -> bool:
    """用 adb input swipe 小幅拖进度条，不必拉满。"""
    box = _parse_bounds(el.attrib.get("bounds") or "")
    if not box:
        return False
    x1, y1, x2, y2 = box
    width = x2 - x1
    y = (y1 + y2) // 2
    travel = max(80, int(width * 0.18))
    start = x1 + int(width * 0.40)
    end = min(x2 - 16, start + travel)
    if end - start < 48:
        start, end = x1 + 24, min(x2 - 16, x1 + 24 + 80)
    return input_swipe(serial, start, y, end, y, 280)


def _locate_one_volume_bar(serial: str, descs: tuple[str, ...]) -> ET.Element | None:
    xml = _dump_xml(serial)
    el = _best_slider_for_descs(xml, descs)
    if el is not None:
        return el
    _swipe_screen_up(serial)
    time.sleep(0.3)
    return _best_slider_for_descs(_dump_xml(serial), descs)


def _check_after_action(
    serial: str,
    kind: str,
    token: str,
    settle: float = 0.6,
    timeout: float = 5.0,
) -> tuple[bool, str, str]:
    deadline = time.time() + timeout
    time.sleep(settle)
    last = ""
    while True:
        last = _dmesg_pa(serial, kind)
        if _token_hit(last, token, kind=kind):
            break
        if time.time() >= deadline:
            break
        time.sleep(0.4)
    hits = _format_hits(kind, last)
    preview = (last or "")[-500:].replace("\n", " | ")
    return _token_hit(last, token, kind=kind), hits, preview


def _tap_speaker(serial: str) -> bool:
    xml = _dump_xml(serial)
    if not xml:
        return False
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return False
    candidates: list[ET.Element] = []
    for el in root.iter("node"):
        desc = (el.attrib.get("content-desc") or "").strip()
        text = (el.attrib.get("text") or "").strip()
        rid = (el.attrib.get("resource-id") or "").lower()
        if desc in _SPEAKER_DESCS or text in _SPEAKER_DESCS:
            candidates.append(el)
            continue
        if any(frag in rid for frag in _SPEAKER_RID_FRAGS):
            candidates.append(el)
    for el in candidates:
        if not _node_size_ok(el):
            continue
        try:
            cx, cy = parse_bounds_center(el.attrib.get("bounds") or "")
        except ValueError:
            continue
        ret = adb_run(serial, "shell", "input", "tap", str(cx), str(cy))
        if ret.returncode == 0:
            time.sleep(0.8)
            return True
    return False


def test_pa_mode(
    serial: str,
    *,
    steps: list[str],
    step_update: StepFn | None = None,
    **_,
) -> dict[str, Any]:
    """
    PA模式检查
    1. cat /odm/etc/vconfig/audio/TranAudioConfiguration.conf 识别 fsm / aw/oca
    2. 每次判定前 dmesg -C；fsm 只 grep fsm_speaker_on
    3. SOUND_SETTINGS 滑动媒体/通知/铃声/闹钟
    4. 拨打 10086 听筒再切免提
    """
    name = "PA模式检查"
    failed: list[str] = []
    passed: list[str] = []

    try:
        emit(step_update, steps, "[PA] 亮屏解锁")
        if not ensure_screen_on_and_unlocked(serial):
            emit(step_update, steps, "[PA] 亮屏解锁-失败")
            return _item(name, "fail", "亮屏解锁失败")
        emit(step_update, steps, "[PA] 亮屏解锁-成功")

        emit(step_update, steps, "[PA] 读取 TranAudioConfiguration.conf")
        conf_path, conf = _read_conf(serial)
        if not conf:
            emit(step_update, steps, "[PA]-失败")
            return _item(name, "fail", f"未找到 {conf_path}")
        emit(step_update, steps, f"[PA] 配置文件: {conf_path}")

        kind, kind_msg = detect_pa_kind(conf)
        emit(step_update, steps, f"[PA] 识别结果: {kind} ({kind_msg})")
        if kind == "unknown":
            emit(step_update, steps, "[PA]-失败")
            return _item(name, "fail", f"无法判断 PA 类型: {kind_msg}")

        expect = _EXPECT[kind]
        emit(step_update, steps, "[PA] 尝试 adb root（dmesg -C 需要）")
        root_ok, root_msg = try_adb_root(serial)
        emit(step_update, steps, f"[PA] adb root: {root_msg or ('ok' if root_ok else '失败')}")

        emit(step_update, steps, "[PA] 打开 android.settings.SOUND_SETTINGS")
        ok, err = _open_sound_settings(serial)
        if not ok:
            emit(step_update, steps, "[PA] 打开声音设置-失败")
            return _item(name, "fail", err)
        emit(step_update, steps, "[PA] 打开声音设置-成功")

        for label, descs in _VOLUME_BARS:
            key = _VOLUME_KEYS[label]
            token = expect[key]
            emit(step_update, steps, f"[PA] 滑动{label}音量条，期望 {token}")
            bar = _locate_one_volume_bar(serial, descs)
            if bar is None:
                msg = f"{label}音量条未找到"
                emit(step_update, steps, f"[PA] {msg}")
                failed.append(msg)
                continue
            box = _parse_bounds(bar.attrib.get("bounds") or "")
            emit(
                step_update,
                steps,
                f"[PA] {label} 控件 {_rid_name(bar) or bar.attrib.get('class', '').split('.')[-1]} bounds={box}",
            )
            cleared, clear_msg = _dmesg_clear(serial)
            if not cleared:
                failed.append(f"{label}: dmesg -C 失败 {clear_msg}")
                emit(step_update, steps, f"[PA] {label} dmesg -C 失败")
                continue
            if not _swipe_seekbar(serial, bar):
                failed.append(f"{label}音量条滑动失败")
                emit(step_update, steps, f"[PA] {label}滑动-失败")
                continue
            hit, hits, preview = _check_after_action(serial, kind, token)
            if not hit:
                bar2 = _locate_one_volume_bar(serial, descs) or bar
                _swipe_seekbar(serial, bar2)
                hit, hits, preview = _check_after_action(
                    serial, kind, token, settle=0.3, timeout=3.0
                )
            emit(step_update, steps, f"[PA] {label} 读到 {hits or '<空>'} | {preview or '<空>'}")
            if hit:
                emit(step_update, steps, f"[PA] {label}-成功 ({token})")
                passed.append(f"{label}:{token}")
            else:
                emit(step_update, steps, f"[PA] {label}-失败 未出现 {token}")
                failed.append(f"{label}未出现 {token}（读到 {hits or '<空>'}）")

        emit(step_update, steps, "[PA] 拨打运营商 10086（听筒）")
        _end_call(serial)
        time.sleep(0.4)
        cleared, clear_msg = _dmesg_clear(serial)
        if not cleared:
            failed.append(f"通话前 dmesg -C 失败 {clear_msg}")
            emit(step_update, steps, "[PA] 通话前 dmesg -C 失败")
        elif not _start_call_10086(serial):
            emit(step_update, steps, "[PA] 拨打10086-失败")
            failed.append("拨打10086失败")
        else:
            deadline = time.time() + 12.0
            while time.time() < deadline and not _call_offhook(serial):
                time.sleep(0.6)
            offhook = _call_offhook(serial)
            emit(step_update, steps, f"[PA] 通话状态 offhook={offhook}")
            hit, hits, preview = _check_after_action(
                serial, kind, expect["handset"], settle=0.3, timeout=5.0
            )
            emit(step_update, steps, f"[PA] 听筒 读到 {hits or '<空>'} | {preview or '<空>'}")
            if hit:
                passed.append(f"听筒:{expect['handset']}")
                emit(step_update, steps, "[PA] 听筒模式-成功")
            else:
                failed.append(f"听筒未出现 {expect['handset']}（读到 {hits or '<空>'}）")
                emit(step_update, steps, "[PA] 听筒模式-失败")

            emit(step_update, steps, "[PA] 切换免提/扬声器")
            cleared, clear_msg = _dmesg_clear(serial)
            if not cleared:
                failed.append(f"免提前 dmesg -C 失败 {clear_msg}")
                emit(step_update, steps, "[PA] 免提前 dmesg -C 失败")
            elif not _tap_speaker(serial):
                emit(step_update, steps, "[PA] 未点到扬声器按钮")
                failed.append("未点到扬声器按钮")
            else:
                hit, hits, preview = _check_after_action(
                    serial, kind, expect["speaker"], settle=0.6, timeout=5.0
                )
                emit(step_update, steps, f"[PA] 免提 读到 {hits or '<空>'} | {preview or '<空>'}")
                if hit:
                    passed.append(f"免提:{expect['speaker']}")
                    emit(step_update, steps, "[PA] 免提模式-成功")
                else:
                    failed.append(f"免提未出现 {expect['speaker']}（读到 {hits or '<空>'}）")
                    emit(step_update, steps, "[PA] 免提模式-失败")
        _end_call(serial)

        if failed:
            emit(step_update, steps, f"[{name}]-失败")
            return _item(
                name,
                "fail",
                f"PA={kind}; 失败: {'; '.join(failed)}"
                + (f"；通过: {', '.join(passed)}" if passed else ""),
            )
        emit(step_update, steps, f"[{name}]-成功")
        return _item(name, "pass", f"PA={kind} {kind_msg}；{', '.join(passed)}")
    finally:
        _end_call(serial)
        release_uiautomator2(serial, wait_ready=False)
        adb_run(serial, "shell", "input", "keyevent", "3", timeout=8)
        adb_run(serial, "shell", "am", "force-stop", "com.android.settings", timeout=8)


def test_adsp_call_algo(
    serial: str,
    *,
    steps: list[str],
    step_update: StepFn | None = None,
    **_,
) -> dict[str, Any]:
    """
    实网通话算法检查，是否跑在 adsp 侧
    1. /proc/device-tree/snd-audio-dsp 存在才继续
    2. 拨打运营商客服 10086
    3. cat /sys/kernel/debug/pm_genpd/adsp_top_dormant/current_state 应为 onn-1
    """
    name = "实网通话算法ADSP检查"
    emit(step_update, steps, f"[ADSP] 检查目录 {_DSP_DT}")
    # 必须保留 [ 与 -d、路径与 ] 之间的空格，否则会变成 [-d / ...] 而不是 test
    exists = adb_shell(
        serial,
        "[ -d /proc/device-tree/snd-audio-dsp ] && echo '存在'",
    )
    if "存在" not in (exists or ""):
        emit(step_update, steps, f"[ADSP] {_DSP_DT} 不存在，跳过")
        return _item(name, "skip", f"{_DSP_DT} 不存在，跳过 ADSP 实网通话检查")
    emit(step_update, steps, "[ADSP] snd-audio-dsp 存在")

    emit(step_update, steps, "[ADSP] 尝试 adb root（debugfs 需要）")
    root_ok, root_msg = try_adb_root(serial)
    emit(step_update, steps, f"[ADSP] adb root: {root_msg or ('ok' if root_ok else '失败')}")
    if not root_ok:
        return _item(name, "skip", f"adb root 失败，无法读 debugfs: {root_msg}")

    try:
        emit(step_update, steps, "[ADSP] 亮屏解锁")
        if not ensure_screen_on_and_unlocked(serial):
            emit(step_update, steps, "[ADSP] 亮屏解锁-失败")
            return _item(name, "fail", "亮屏解锁失败")

        emit(step_update, steps, "[ADSP] 拨打运营商 10086")
        _end_call(serial)
        time.sleep(0.4)
        if not _start_call_10086(serial):
            emit(step_update, steps, "[ADSP] 拨打10086-失败")
            return _item(name, "fail", "拨打10086失败")

        deadline = time.time() + 12.0
        while time.time() < deadline and not _call_offhook(serial):
            time.sleep(0.6)
        offhook = _call_offhook(serial)
        emit(step_update, steps, f"[ADSP] 通话状态 offhook={offhook}")
        if not offhook:
            emit(step_update, steps, f"[{name}]-失败")
            return _item(name, "fail", "实网通话未进入摘机，无法判定 ADSP")

        emit(step_update, steps, f"[ADSP] 读取 {_ADSP_STATE}")
        actual = ""
        state_deadline = time.time() + 8.0
        while time.time() < state_deadline:
            raw = (adb_cat(serial, _ADSP_STATE) or "").strip()
            actual = raw.splitlines()[0].strip() if raw else ""
            emit(step_update, steps, f"[ADSP] current_state={actual or '<空>'}")
            if actual == _EXPECT_ADSP_ON:
                break
            time.sleep(0.8)

        if actual == _EXPECT_ADSP_ON:
            emit(step_update, steps, f"[{name}]-成功")
            return _item(name, "pass", f"{_ADSP_STATE}={_EXPECT_ADSP_ON}")
        emit(step_update, steps, f"[{name}]-失败")
        return _item(
            name,
            "fail",
            f"expected {_EXPECT_ADSP_ON}（非 off-0）; actual: {actual or '<空>'}",
        )
    finally:
        _end_call(serial)


AUDIO_TEST_CASES = (
    test_audio_param_path,
    test_dts_tuning_path,
    test_recording_function,
    test_pa_mode,
    test_adsp_call_algo,
)


def run_all_test_cases(
    serial: str,
    *,
    step_update: StepFn | None = None,
    result_dir=None,
) -> tuple[list[dict[str, Any]], list[str]]:
    steps = [f"设备: {serial}", "开始执行 音频流水线适配检查"]
    if callable(step_update):
        step_update("\n".join(steps))

    results: list[dict[str, Any]] = []
    for fn in AUDIO_TEST_CASES:
        result = fn(serial, steps=steps, step_update=step_update, result_dir=result_dir)
        results.append(result)
        suffix = _STATUS_SUFFIX.get(str(result.get("status")), str(result.get("status")))
        emit(step_update, steps, f"{result.get('name')}-{suffix}")
    return results, steps
