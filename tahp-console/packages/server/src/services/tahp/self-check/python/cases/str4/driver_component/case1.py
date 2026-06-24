"""STR4 驱动器件：TP 固件版本和算法版本（sysfs + 工模硬件信息页）。"""

import re
import time
import xml.etree.ElementTree as ET

from utils.driver.tranfacmode_ui import adb, dump, poll_bool, tap_xml, ui_has_keywords
from utils.driver.ui_tranfacmode import (
    skip_rf_calibration,
    start_main,
    tranfacmode_prep_steps,
)
from utils.tdd.ui_automatic import (
    DEFAULT_SLEEP_AFTER_SWIPE,
    DEFAULT_SWIPE,
    _ensure_device_scroll_index,
    acquire_u2,
    click_by_match_keywords,
    dump_current_ui,
    release_uiautomator2,
)

TP_FIRMWARE_NODE = "/sys/devices/platform/mtk-tpd/tp_firmware_version"
MENU_DRAWER_RID = "com.transsion.tranfacmode:id/menu_drawer"
ADAPTER_SUMMARY_SUFFIX = "adapter_summary"
HARDWARE_INFO_KEYWORDS = ("硬件信息", "Hardware Info")
TP_INFO_KEYWORDS = ("TP Info", "TP信息")
HARDWARE_PAGE_KEYWORDS = ("硬件信息", "Hardware Info", "TP Info", "TP信息")
MAX_HARDWARE_INFO_SCROLLS = 12
_LIST_SWIPE = (*DEFAULT_SWIPE[:4], DEFAULT_SWIPE[4])


def _get_dut_device_id(device_info):
    dut_list = (device_info or {}).get("DUT") or []
    if not dut_list:
        return None, "未获取到测试机设备信息"
    dut_id = (dut_list[0].get("device_id") or "").strip()
    if not dut_id:
        return None, "测试机 device_id 为空"
    return dut_id, ""


def _parent_map(root: ET.Element) -> dict:
    parent: dict = {}
    for node in root.iter():
        for child in list(node):
            parent[child] = node
    return parent


def _read_sysfs_firmware(device_id: str) -> tuple[bool, str]:
    ret = adb(device_id, "shell", "cat", TP_FIRMWARE_NODE)
    if ret.returncode != 0:
        detail = (ret.stderr or ret.stdout or "").strip()
        return False, detail or "读取 tp_firmware_version 失败"
    text = (ret.stdout or "").strip()
    if not text:
        return False, "tp_firmware_version 节点内容为空"
    return True, text


def _normalize_fw_punctuation(text: str) -> str:
    """工模 UI 常用全角冒号/逗号，统一为半角便于解析。"""
    return (
        (text or "")
        .replace("：", ":")
        .replace("，", ",")
        .replace("；", ";")
    )


def _extract_fw_version_segment(text: str) -> str:
    """从整段摘要中提取含 bv 的固件版本子串。"""
    raw = (text or "").strip()
    if not raw:
        return ""
    for line in raw.replace("\r", "\n").split("\n"):
        candidate = line.strip()
        if re.search(r"bv[：:]", candidate, flags=re.I) and re.search(
            r"0x", candidate, flags=re.I
        ):
            return candidate
    match = re.search(
        r"0x[0-9a-fA-F_]+[,，]?\s*bv[：:]\s*0x[0-9a-fA-F_]+",
        raw,
        flags=re.I,
    )
    return match.group(0) if match else raw


def _extract_fw_bv_hex(text: str) -> tuple[str, str]:
    """提取第一个固件 0x 值与 bv 后的 0x 值（支持 Firmware：0x24，bv：0x24）。"""
    raw = _normalize_fw_punctuation(_extract_fw_version_segment(text))
    if not raw:
        return "", ""

    match = re.search(r"bv:\s*(.+)", raw, flags=re.I)
    if match:
        fw_region = raw[: match.start()]
        bv_region = match.group(1)
        fw_match = re.search(r"0x[0-9a-fA-F]+(?:_0x[0-9a-fA-F]+)?", fw_region, flags=re.I)
        bv_match = re.search(r"0x[0-9a-fA-F]+(?:_0x[0-9a-fA-F]+)?", bv_region, flags=re.I)
        if fw_match and bv_match:
            return fw_match.group(0).lower(), bv_match.group(0).lower()

    hex_values = re.findall(r"0x[0-9a-fA-F]+(?:_0x[0-9a-fA-F]+)?", raw, flags=re.I)
    if len(hex_values) >= 2:
        return hex_values[0].lower(), hex_values[1].lower()
    return "", ""


def _fw_bv_consistent(text: str) -> tuple[bool, str, str]:
    fw_hex, bv_hex = _extract_fw_bv_hex(text)
    if not fw_hex or not bv_hex:
        return False, fw_hex, bv_hex
    return fw_hex == bv_hex, fw_hex, bv_hex


def _ic_display_ok(summary: str) -> bool:
    text = (summary or "").strip()
    if not text:
        return False
    upper = text.upper()
    if "UNKNOWN" in upper:
        return False
    if re.search(r"\bN/?A\b", upper):
        return False
    return True


def _is_tp_info_label(text: str) -> bool:
    label = (text or "").strip()
    if not label:
        return False
    for keyword in TP_INFO_KEYWORDS:
        if keyword in label or label in keyword:
            return True
    return False


def _find_tp_info_summary(xml: ET.ElementTree) -> str:
    root = xml.getroot()
    parent = _parent_map(root)
    for el in root.iter("node"):
        label = (el.attrib.get("text") or "").strip()
        desc = (el.attrib.get("content-desc") or "").strip()
        if not _is_tp_info_label(label) and not _is_tp_info_label(desc):
            continue
        cur = el
        for _ in range(10):
            cur = parent.get(cur)
            if cur is None:
                break
            node_class = cur.attrib.get("class") or ""
            if "ViewGroup" not in node_class:
                continue
            for child in cur.iter("node"):
                rid = child.attrib.get("resource-id") or ""
                if ADAPTER_SUMMARY_SUFFIX not in rid:
                    continue
                summary = (child.attrib.get("text") or "").strip()
                if summary:
                    return summary
            break
    return ""


def _swipe_hardware_info_list_once(device_id: str) -> None:
    x1, y1, x2, y2, duration_ms = _LIST_SWIPE
    adb(device_id, "shell", "input", "swipe", x1, y1, x2, y2, str(duration_ms))
    time.sleep(DEFAULT_SLEEP_AFTER_SWIPE)


def _read_tp_info_from_screen(device_id: str) -> str:
    xml_path = dump_current_ui(device_id) or dump(device_id)
    if not xml_path:
        return ""
    return _find_tp_info_summary(ET.parse(xml_path))


def _scroll_and_find_tp_info(device_id: str) -> tuple[bool, str]:
    """硬件信息页向下滑动查找 TP Info 摘要。"""
    use_u2 = acquire_u2(device_id) is not None
    scroll_count = 0
    try:
        for slide in range(MAX_HARDWARE_INFO_SCROLLS + 1):
            summary = _read_tp_info_from_screen(device_id)
            if summary:
                return True, summary
            if slide >= MAX_HARDWARE_INFO_SCROLLS:
                break
            if use_u2:
                scroll_count = _ensure_device_scroll_index(
                    device_id,
                    slide + 1,
                    scroll_count,
                    _LIST_SWIPE,
                    DEFAULT_SLEEP_AFTER_SWIPE,
                )
            else:
                _swipe_hardware_info_list_once(device_id)
        summary = _read_tp_info_from_screen(device_id)
        return bool(summary), summary
    finally:
        if use_u2:
            release_uiautomator2(device_id, wait_ready=False)


def _open_menu_drawer(device_id: str) -> bool:
    xml = dump(device_id)
    if not xml:
        return False
    return tap_xml(device_id, xml, resource_id=MENU_DRAWER_RID)


def _enter_hardware_info(device_id: str) -> bool:
    if not _open_menu_drawer(device_id):
        return False
    time.sleep(0.45)
    if not click_by_match_keywords(
        device_id,
        HARDWARE_INFO_KEYWORDS,
        max_scrolls=4,
        sleep_after_swipe=0.5,
        sleep_after_tap=0.55,
        prefer_cached_ui=False,
    ):
        return False
    return poll_bool(
        lambda: (x := dump(device_id)) is not None
        and ui_has_keywords(x, HARDWARE_PAGE_KEYWORDS),
        8.0,
        0.35,
    )


def run(category=None, case_index=None, device_info=None, **context):
    step_update = context.get("step_update")
    device_info = device_info or context.get("device_info") or {}

    dut_id, error = _get_dut_device_id(device_info)
    if not dut_id:
        if callable(step_update):
            step_update(error)
        return {"status": "fail", "message": error}

    sub_steps = ""

    def on_step(label: str, ok: bool) -> None:
        nonlocal sub_steps
        sub_steps += f"\n{label}" + ("-成功" if ok else "-失败")
        if callable(step_update):
            step_update(sub_steps)

    sysfs_ok, sysfs_text = _read_sysfs_firmware(dut_id)
    on_step("读取 sysfs tp_firmware_version", sysfs_ok)
    if not sysfs_ok:
        return {"status": "fail", "message": f"sysfs 读取失败: {sysfs_text}"}

    sub_steps += f"\nsysfs: {sysfs_text}"
    if callable(step_update):
        step_update(sub_steps)

    sysfs_consistent, sysfs_fw, sysfs_bv = _fw_bv_consistent(sysfs_text)
    on_step(
        f"sysfs 固件版本一致(fw={sysfs_fw or '-'}, bv={sysfs_bv or '-'})",
        sysfs_consistent,
    )
    if not sysfs_consistent:
        return {
            "status": "fail",
            "message": f"sysfs 固件版本不一致: {sysfs_text}",
        }

    pre_steps = [
        *tranfacmode_prep_steps(dut_id),
        ("启动工模主界面", lambda: start_main(dut_id), "启动工模 MainActivity 失败"),
        ("跳过射频参数校准", lambda: skip_rf_calibration(dut_id), "跳过射频参数校准失败"),
        ("进入硬件信息界面", lambda: _enter_hardware_info(dut_id), "进入硬件信息界面失败"),
    ]
    for label, action, fail_msg in pre_steps:
        ok = action()
        on_step(label, ok)
        if not ok:
            return {"status": "fail", "message": fail_msg}

    ui_ok, ui_summary = _scroll_and_find_tp_info(dut_id)
    on_step("向下滑动查找 TP Info", ui_ok)
    if not ui_ok:
        return {"status": "fail", "message": "未在硬件信息页找到 TP Info 摘要"}

    sub_steps += f"\n工模 TP 摘要: {ui_summary}"
    if callable(step_update):
        step_update(sub_steps)

    ic_ok = _ic_display_ok(ui_summary)
    on_step("工模 IC 信息显示正常", ic_ok)
    if not ic_ok:
        return {"status": "fail", "message": f"工模 IC 信息显示异常: {ui_summary}"}

    ui_consistent, ui_fw, ui_bv = _fw_bv_consistent(ui_summary)
    on_step(
        f"工模固件版本一致(fw={ui_fw or '-'}, bv={ui_bv or '-'})",
        ui_consistent,
    )
    if not ui_consistent:
        return {
            "status": "fail",
            "message": f"工模固件版本不一致: {ui_summary}",
        }

    return {
        "status": "pass",
        "message": (
            f"TP 固件版本检查通过；sysfs={sysfs_text}；工模={ui_summary}"
        ),
    }
