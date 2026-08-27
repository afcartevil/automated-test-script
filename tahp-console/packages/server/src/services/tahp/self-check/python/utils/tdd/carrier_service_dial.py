"""按插入 SIM（优先卡1）识别运营商并拨打客服服务号码。

供 pipeline_adapt/tdd 等适配流水线用例复用。

生产机 adb shell 通常无 CALL_PHONE，android.intent.action.CALL 不会真正起呼；
因此走 DIAL 打开拨号盘预填号码 → 点击「拨打」→ 确认进入通话后再挂断。
"""

from __future__ import annotations

import re
import subprocess
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from utils.tdd.ui_automatic import dump_current_ui, ensure_screen_on_and_unlocked
from utils.tdd.ui_xml import parse_bounds_center

_SIM_READY = frozenset({"LOADED", "READY"})

# 中国大陆常见 MCC+MNC → (运营商名, 服务号码)
_NUMERIC_TO_CARRIER: dict[str, tuple[str, str]] = {
    "46000": ("中国移动", "10086"),
    "46002": ("中国移动", "10086"),
    "46004": ("中国移动", "10086"),
    "46007": ("中国移动", "10086"),
    "46008": ("中国移动", "10086"),
    "46013": ("中国移动", "10086"),
    "46001": ("中国联通", "10010"),
    "46006": ("中国联通", "10010"),
    "46009": ("中国联通", "10010"),
    "46010": ("中国联通", "10010"),
    "46003": ("中国电信", "10000"),
    "46005": ("中国电信", "10000"),
    "46011": ("中国电信", "10000"),
    "46012": ("中国电信", "10000"),
    "46015": ("中国广电", "10099"),
}

_NAME_RULES: tuple[tuple[tuple[str, ...], str, str], ...] = (
    (("中国移动", "移动", "cmcc", "china mobile"), "中国移动", "10086"),
    (("中国联通", "联通", "cucc", "china unicom"), "中国联通", "10010"),
    (("中国电信", "电信", "ctcc", "china telecom"), "中国电信", "10000"),
    (("中国广电", "广电", "cbn", "china broadcasting"), "中国广电", "10099"),
)

_DIALER_PKG = "com.sh.smart.caller"
_RID_DIGITS = f"{_DIALER_PKG}:id/digits"
_RID_DIAL_FAB = f"{_DIALER_PKG}:id/dialpad_floating_action_button"
_RID_END_CALL = f"{_DIALER_PKG}:id/incall_end_call"
_RID_INCALL = f"{_DIALER_PKG}:id/incall_fragment"
_RID_STATUS = f"{_DIALER_PKG}:id/contactgrid_status_text"
_RID_BOTTOM = f"{_DIALER_PKG}:id/contactgrid_bottom_text"


@dataclass(frozen=True)
class SimCarrierChoice:
    slot: int  # 0-based
    slot_label: str
    state: str
    alpha: str
    numeric: str
    carrier: str
    service_number: str


def _adb_shell(device_id: str, command: str, *, timeout: int = 30) -> str:
    ret = subprocess.run(
        ["adb", "-s", device_id, "shell", command],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    out = (ret.stdout or "").strip()
    return out or (ret.stderr or "").strip()


def _adb_run(device_id: str, *args: str, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["adb", "-s", device_id, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )


def _split_csv_prop(raw: str) -> list[str]:
    return [p.strip() for p in re.split(r"[,;]", raw or "")]


def resolve_carrier_service(alpha: str, numeric: str) -> Optional[tuple[str, str]]:
    """根据运营商 alpha / MCCMNC 解析 (运营商名, 服务号码)。"""
    num = re.sub(r"\D", "", numeric or "")
    if num in _NUMERIC_TO_CARRIER:
        return _NUMERIC_TO_CARRIER[num]
    if len(num) >= 5 and num[:5] in _NUMERIC_TO_CARRIER:
        return _NUMERIC_TO_CARRIER[num[:5]]

    name = (alpha or "").strip().lower()
    if name:
        for keywords, carrier, number in _NAME_RULES:
            if any(k.lower() in name for k in keywords):
                return carrier, number
    return None


def pick_preferred_sim(device_id: str) -> tuple[Optional[SimCarrierChoice], str]:
    """
    选择优先 SIM：卡1 已插且就绪则用卡1，否则用卡2（及后续槽位）中第一个就绪卡。
    返回 (choice, detail)；无卡或无法映射时 choice 为 None。
    """
    states = _split_csv_prop(_adb_shell(device_id, "getprop gsm.sim.state"))
    alphas = _split_csv_prop(_adb_shell(device_id, "getprop gsm.sim.operator.alpha"))
    numerics = _split_csv_prop(_adb_shell(device_id, "getprop gsm.sim.operator.numeric"))

    slot_count = max(len(states), len(alphas), len(numerics), 2)
    while len(states) < slot_count:
        states.append("")
    while len(alphas) < slot_count:
        alphas.append("")
    while len(numerics) < slot_count:
        numerics.append("")

    ready_slots: list[int] = []
    for idx in range(slot_count):
        st = (states[idx] or "").strip().upper()
        if st in _SIM_READY:
            ready_slots.append(idx)

    if not ready_slots:
        detail = (
            f"gsm.sim.state={','.join(states) or '<空>'}; "
            f"alpha={','.join(alphas)}; numeric={','.join(numerics)}"
        )
        return None, detail

    slot = 0 if 0 in ready_slots else ready_slots[0]
    alpha = alphas[slot] if slot < len(alphas) else ""
    numeric = numerics[slot] if slot < len(numerics) else ""
    state = states[slot] if slot < len(states) else ""
    resolved = resolve_carrier_service(alpha, numeric)
    if not resolved:
        detail = (
            f"卡{slot + 1} state={state} alpha={alpha!r} numeric={numeric!r} "
            f"无法映射运营商服务号码"
        )
        return None, detail

    carrier, number = resolved
    choice = SimCarrierChoice(
        slot=slot,
        slot_label=f"卡{slot + 1}",
        state=state,
        alpha=alpha,
        numeric=numeric,
        carrier=carrier,
        service_number=number,
    )
    detail = (
        f"{choice.slot_label} {choice.carrier}({choice.numeric or choice.alpha}) "
        f"→ {choice.service_number}"
    )
    return choice, detail


def _best_effort_set_voice_slot(device_id: str, slot: int) -> None:
    """尽量把默认语音卡设到目标槽位（subscription id 常见为 slot+1）。"""
    sub_id = slot + 1
    _adb_shell(device_id, f"settings put global multi_sim_voice_call {sub_id}")
    time.sleep(0.3)


def _looks_like_keyguard(xml: Path) -> bool:
    """部分机型 dumpsys trust 已 unlocked，但 UI 仍停在锁屏/充电表盘。"""
    root = ET.parse(xml).getroot()
    pkgs = {(el.attrib.get("package") or "") for el in root.iter("node")}
    pkgs.discard("")
    if pkgs and pkgs <= {"com.android.systemui"}:
        return True
    for el in root.iter("node"):
        rid = el.attrib.get("resource-id") or ""
        if any(
            k in rid
            for k in (
                "keyguard_indication",
                "clock_time_hour",
                "keyguard_carrier_text",
                "lock_icon",
            )
        ):
            return True
    return False


def _force_dismiss_lockscreen(device_id: str) -> None:
    """强制亮屏上滑 + dismiss-keyguard（弥补 DreamingLockscreen 误判）。"""
    _adb_run(device_id, "shell", "input", "keyevent", "KEYCODE_WAKEUP", timeout=8)
    time.sleep(0.2)
    for _ in range(3):
        _adb_run(device_id, "shell", "input", "keyevent", "82", timeout=8)
        _adb_run(
            device_id,
            "shell",
            "input",
            "swipe",
            "540",
            "1800",
            "540",
            "500",
            "250",
            timeout=8,
        )
        _adb_run(device_id, "shell", "wm", "dismiss-keyguard", timeout=8)
        time.sleep(0.45)
        xml = dump_current_ui(device_id)
        if xml and not _looks_like_keyguard(xml):
            return


def _tap_bounds(device_id: str, bounds: str) -> bool:
    if not bounds:
        return False
    try:
        cx, cy = parse_bounds_center(bounds)
    except ValueError:
        return False
    ret = _adb_run(device_id, "shell", "input", "tap", str(cx), str(cy), timeout=8)
    return ret.returncode == 0


def _find_node(
    root: ET.Element,
    *,
    resource_id: str = "",
    text_equals: tuple[str, ...] = (),
    desc_equals: tuple[str, ...] = (),
    text_contains: tuple[str, ...] = (),
) -> Optional[ET.Element]:
    for el in root.iter("node"):
        rid = el.attrib.get("resource-id") or ""
        text = (el.attrib.get("text") or "").strip()
        desc = (el.attrib.get("content-desc") or "").strip()
        if resource_id and rid == resource_id:
            return el
        if text_equals and text in text_equals:
            return el
        if desc_equals and desc in desc_equals:
            return el
        if text_contains and any(k in text for k in text_contains):
            return el
    return None


def _open_dialer_with_number(device_id: str, number: str) -> bool:
    num = re.sub(r"\D", "", number or "")
    if not num:
        return False
    _force_dismiss_lockscreen(device_id)
    _adb_run(device_id, "shell", "input", "keyevent", "KEYCODE_HOME", timeout=8)
    time.sleep(0.3)
    _adb_run(device_id, "shell", "am", "force-stop", _DIALER_PKG, timeout=10)
    time.sleep(0.4)
    ret = _adb_run(
        device_id,
        "shell",
        "am",
        "start",
        "-a",
        "android.intent.action.DIAL",
        "-d",
        f"tel:{num}",
        timeout=15,
    )
    out = f"{ret.stdout or ''}{ret.stderr or ''}"
    if ret.returncode != 0 or "Error" in out or "Exception" in out:
        return False
    time.sleep(1.5)

    deadline = time.time() + 12.0
    while time.time() < deadline:
        xml = dump_current_ui(device_id)
        if not xml:
            time.sleep(0.4)
            continue
        if _looks_like_keyguard(xml):
            _force_dismiss_lockscreen(device_id)
            _adb_run(
                device_id,
                "shell",
                "am",
                "start",
                "-a",
                "android.intent.action.DIAL",
                "-d",
                f"tel:{num}",
                timeout=15,
            )
            time.sleep(1.0)
            continue
        root = ET.parse(xml).getroot()
        digits = _find_node(root, resource_id=_RID_DIGITS)
        if digits is not None:
            shown = re.sub(r"\D", "", digits.attrib.get("text") or "")
            if shown.endswith(num) or num in shown:
                return True
        # 拨号盘未展开时点「打开拨号盘」
        fab = _find_node(root, resource_id=f"{_DIALER_PKG}:id/fab") or _find_node(
            root, desc_equals=("打开拨号盘", "Dialpad")
        )
        if fab is not None:
            _tap_bounds(device_id, fab.attrib.get("bounds") or "")
            time.sleep(0.8)
            continue
        time.sleep(0.4)
    return False


def _tap_dial_button(device_id: str) -> bool:
    xml = dump_current_ui(device_id)
    if not xml:
        return False
    root = ET.parse(xml).getroot()
    btn = _find_node(root, resource_id=_RID_DIAL_FAB) or _find_node(
        root, desc_equals=("拨打", "Call", "call")
    )
    if btn is None:
        return False
    return _tap_bounds(device_id, btn.attrib.get("bounds") or "")


def _maybe_pick_sim_in_chooser(device_id: str, choice: SimCarrierChoice) -> None:
    """双卡拨号若弹出选卡框，尽量点选目标卡/运营商。"""
    time.sleep(0.8)
    xml = dump_current_ui(device_id)
    if not xml:
        return
    root = ET.parse(xml).getroot()
    # 已进入通话则无需选卡
    if _find_node(root, resource_id=_RID_INCALL) is not None:
        return

    prefer_labels = (
        choice.slot_label,
        f"SIM{choice.slot + 1}",
        f"SIM {choice.slot + 1}",
        choice.carrier,
        choice.alpha,
    )
    prefer_labels = tuple(x for x in prefer_labels if x)
    for label in prefer_labels:
        node = _find_node(root, text_equals=(label,), text_contains=(label,))
        if node is not None and (node.attrib.get("clickable") == "true" or True):
            # 优先点可点击节点；否则点其本身
            target = node
            if node.attrib.get("clickable") != "true":
                # 尝试父级可点击：简化为直接 tap bounds
                pass
            if _tap_bounds(device_id, target.attrib.get("bounds") or ""):
                time.sleep(0.8)
                return


def call_offhook(device_id: str) -> bool:
    text = _adb_shell(
        device_id,
        "dumpsys telephony.registry 2>/dev/null | grep mCallState",
        timeout=15,
    )
    return bool(re.search(r"mCallState=[12]\b", text or ""))


def in_call_ui(device_id: str, number: str = "") -> bool:
    xml = dump_current_ui(device_id)
    if not xml:
        return False
    root = ET.parse(xml).getroot()
    if _find_node(root, resource_id=_RID_INCALL) is not None:
        return True
    if _find_node(root, resource_id=_RID_END_CALL) is not None:
        return True
    status = _find_node(root, resource_id=_RID_STATUS)
    if status is not None:
        st = (status.attrib.get("text") or "").strip()
        if any(k in st for k in ("正在呼叫", "通话中", "Calling", "Connected")):
            return True
    if number:
        bottom = _find_node(root, resource_id=_RID_BOTTOM)
        if bottom is not None and number in (bottom.attrib.get("text") or ""):
            return True
    return False


def wait_call_connected(
    device_id: str,
    number: str,
    *,
    timeout_s: float = 20.0,
) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if call_offhook(device_id) or in_call_ui(device_id, number):
            return True
        time.sleep(0.5)
    return False


def end_call(device_id: str) -> None:
    xml = dump_current_ui(device_id)
    if xml:
        root = ET.parse(xml).getroot()
        end_btn = _find_node(root, resource_id=_RID_END_CALL) or _find_node(
            root, desc_equals=("结束通话", "End call", "Hang up")
        )
        if end_btn is not None:
            _tap_bounds(device_id, end_btn.attrib.get("bounds") or "")
            time.sleep(0.4)
    _adb_run(device_id, "shell", "input", "keyevent", "KEYCODE_ENDCALL", timeout=8)
    time.sleep(0.3)
    _adb_run(device_id, "shell", "input", "keyevent", "KEYCODE_ENDCALL", timeout=8)


def dial_carrier_service_number(
    device_id: str,
    *,
    result_dir=None,
    ring_seconds: float = 3.0,
    connect_timeout_s: float = 20.0,
) -> dict:
    """
    识别优先 SIM 运营商并拨打服务号码，确认进入通话后再挂断。

    返回 dict: status(pass|fail|skip), message, choice
    """
    if result_dir:
        from utils.tdd.ui_paths import set_ui_result_dir

        set_ui_result_dir(result_dir)

    choice, detail = pick_preferred_sim(device_id)
    if choice is None:
        if "无法映射" in detail:
            return {"status": "fail", "message": detail, "choice": None}
        return {
            "status": "skip",
            "message": f"未插入SIM卡，跳过拨打运营商服务号码（{detail}）",
            "choice": None,
        }

    ensure_screen_on_and_unlocked(device_id)
    _force_dismiss_lockscreen(device_id)
    _best_effort_set_voice_slot(device_id, choice.slot)

    if not _open_dialer_with_number(device_id, choice.service_number):
        return {
            "status": "fail",
            "message": f"打开拨号盘并预填号码失败: {detail}",
            "choice": choice,
        }

    if not _tap_dial_button(device_id):
        return {
            "status": "fail",
            "message": f"点击拨打按钮失败: {detail}",
            "choice": choice,
        }

    _maybe_pick_sim_in_chooser(device_id, choice)

    if not wait_call_connected(
        device_id,
        choice.service_number,
        timeout_s=connect_timeout_s,
    ):
        end_call(device_id)
        return {
            "status": "fail",
            "message": f"已发起拨号但未进入通话: {detail}",
            "choice": choice,
        }

    if ring_seconds > 0:
        time.sleep(ring_seconds)
    end_call(device_id)
    return {
        "status": "pass",
        "message": f"已拨通 {detail}",
        "choice": choice,
    }
