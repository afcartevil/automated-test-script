"""pipeline_adapt / TP 用例列表（由 case1 顺序编排执行）。"""

from __future__ import annotations

import re
from typing import Any

from _common import StepFn, adb_cat, adb_shell, emit, try_adb_root
from utils.driver.tranfacmode_config import SCREEN_TOUCH_SELF_ITEM_KEYWORDS
from utils.driver.ui_tranfacmode import close_tranfacmode, go_home, run_screen_group_item_test

_FIRMWARE_RE = re.compile(r"0x[0-9a-fA-F]+,bv:0x[0-9a-fA-F]+(?:\s+Algo:[\w.\-]+)?")
_VENDOR_RE = re.compile(r"^[A-Z]{2,}_[A-Z0-9]+_\d{2}$")
_FIRMWARE_PATH = "/sys/devices/platform/mtk-tpd/tp_firmware_version"
_VENDOR_PATH = "/sys/devices/platform/mtk-tpd/tp_vendor"
_MTK_TPD = '"mtk-tpd"'

# 对齐 fc-tp-selinux：存在则校验标签与可读；缺失记 MISSING（不单独 Fail）
_TP_PROC_NODES = (
    ("gesture_function", ("proc_gesture",)),
    ("gesture_state", ("proc_gesture",)),
    ("gesture_flag", ("proc_gesture",)),
    ("tp_panel_test", ("proc_nvt_selftest", "proc_main_selftest", "proc_nvt", "proc_tp")),
    ("fingerprint_status", ("proc_fingerprint",)),
    ("tp_large_area_mistouch_switch", ("proc_tp_large_area",)),
    ("tp_scene", ("proc_tp_scene",)),
)


def _item(name: str, status: str, message: str) -> dict[str, Any]:
    return {"name": name, "status": status, "message": message}


def test_firmware_version(serial: str, *, steps: list[str], step_update: StepFn | None = None, **_) -> dict[str, Any]:
    """
    TP基础功能以及信息检查: 获取固件版本节点
    测试步骤: cat /sys/devices/platform/mtk-tpd/tp_firmware_version
    预期结果: 0xxx,bv:0xxx (示例 0x22,bv:0x22) 或 0xxx,bv:0xxx Algo:xxxx.xx.xx-xx
    """
    emit(step_update, steps, f"[固件版本] 读取 {_FIRMWARE_PATH}")
    actual = adb_cat(serial, _FIRMWARE_PATH).strip()
    emit(step_update, steps, f"[固件版本] 输出: {actual or '<空>'}")
    if not actual:
        emit(step_update, steps, "[固件版本]-失败")
        return _item("获取固件版本节点", "fail", "TP固件版本读取失败")
    if not _FIRMWARE_RE.search(actual):
        emit(step_update, steps, "[固件版本]-失败")
        return _item(
            "获取固件版本节点",
            "fail",
            f"格式校验失败: expected like 0x22,bv:0x22; actual: {actual}",
        )
    emit(step_update, steps, "[固件版本]-成功")
    return _item("获取固件版本节点", "pass", actual)


def test_vendor(serial: str, *, steps: list[str], step_update: StepFn | None = None, **_) -> dict[str, Any]:
    """
    TP基础功能以及信息检查: 获取供应商版本节点
    测试步骤: cat /sys/devices/platform/mtk-tpd/tp_vendor
    预期结果: 模块厂商名大写字母_芯片型号_序号 (示例 TM_FT3683G_00)
    """
    emit(step_update, steps, f"[供应商] 读取 {_VENDOR_PATH}")
    actual = adb_cat(serial, _VENDOR_PATH).strip()
    emit(step_update, steps, f"[供应商] 输出: {actual or '<空>'}")
    if not actual:
        emit(step_update, steps, "[供应商]-失败")
        return _item("获取供应商版本节点", "fail", "TP供应商信息读取失败")
    if not _VENDOR_RE.match(actual):
        emit(step_update, steps, "[供应商]-失败")
        return _item(
            "获取供应商版本节点",
            "fail",
            f"格式校验失败: expected like TM_FT3683G_00; actual: {actual}",
        )
    emit(step_update, steps, "[供应商]-成功")
    return _item("获取供应商版本节点", "pass", actual)


def test_mtk_tpd(serial: str, *, steps: list[str], step_update: StepFn | None = None, **_) -> dict[str, Any]:
    """
    TP基础功能以及信息检查: 判断是否加载mtk-tpd
    测试步骤: getevent -li
    预期结果: name:     "mtk-tpd"
    """
    emit(step_update, steps, "[mtk-tpd] 执行 getevent -li")
    actual = adb_shell(serial, "getevent -li", timeout=45)
    preview = (actual or "")[:500].replace("\n", " | ")
    emit(step_update, steps, f"[mtk-tpd] 输出摘要: {preview or '<空>'}")
    if _MTK_TPD not in (actual or ""):
        emit(step_update, steps, "[mtk-tpd]-失败")
        return _item("获取mtk-tpd设备信息", "fail", f"expected contains {_MTK_TPD}")
    emit(step_update, steps, "[mtk-tpd]-成功")
    return _item("获取mtk-tpd设备信息", "pass", 'getevent 输出包含 name: "mtk-tpd"')


def test_se_nodes(serial: str, *, steps: list[str], step_update: StepFn | None = None, **_) -> dict[str, Any]:
    """
    TP SE节点权限检查
    测试步骤: 检查 /proc 下节点是否存在，且节点 SELinux 标签是否正确
    预期结果: 脚本返回 True（无 unlabeled/default_t，无 Permission denied）
    前置: adb root 成功；失败则 skip 本项
    """
    emit(step_update, steps, "[SE节点] 尝试 adb root")
    root_ok, root_msg = try_adb_root(serial)
    if not root_ok:
        emit(step_update, steps, f"[SE节点] adb root 失败，跳过: {root_msg}")
        return _item("SE节点权限检查", "skip", f"adb root 失败，跳过 SE 节点检查: {root_msg}")
    emit(step_update, steps, f"[SE节点] adb root 成功: {root_msg or 'ok'}")
    emit(step_update, steps, "[SE节点] 检查 /proc 下 TP 节点存在性与 SELinux 标签")

    fail = False
    buckets: dict[str, list[str]] = {
        "不存在": [],
        "标签未打标": [],
        "读权限失败": [],
        "标签类型告警": [],
    }

    for node, frags in _TP_PROC_NODES:
        path = f"/proc/{node}"
        ls_out = adb_shell(serial, f"ls -Z {path} 2>&1")
        low = (ls_out or "").lower()
        if "no such file" in low or not ls_out:
            buckets["不存在"].append(path)
            emit(step_update, steps, f"[SE节点] {path}: MISSING")
            continue

        m = re.search(r"(u:[^\s]+)", ls_out)
        label = m.group(1) if m else (ls_out.split()[0] if ls_out.split() else "(unknown)")
        match = "OK"
        if re.search(r"unlabeled|default_t", label):
            match, fail = "FAIL-label", True
            buckets["标签未打标"].append(f"{path}({label})")
        elif not any(f in label for f in frags):
            match = "WARN-type"
            buckets["标签类型告警"].append(f"{path}({label})")

        cat_low = adb_shell(serial, f"cat {path} 2>&1").lower()
        read_st = "OK"
        if "permission denied" in cat_low:
            read_st, match, fail = "DENIED", "FAIL-read", True
            buckets["读权限失败"].append(path)
        elif "no such file" in cat_low:
            read_st, match, fail = "MISSING", "FAIL-read", True
            buckets["不存在"].append(path)

        emit(step_update, steps, f"[SE节点] {path}: label={label} read={read_st} {match}")

    detail_parts = [f"{k}:\n" + "\n".join(v) for k, v in buckets.items() if v]
    detail = "\n".join(detail_parts) if detail_parts else "全部正常"
    if fail:
        emit(step_update, steps, f"[SE节点]-失败:\n{detail}")
        return _item("SE节点权限检查", "fail", detail)
    emit(step_update, steps, f"[SE节点]-成功:\n{detail}")
    return _item("SE节点权限检查", "pass", f"True\n{detail}" if detail_parts else "True")


def test_factory_capacitance(
    serial: str,
    *,
    steps: list[str],
    step_update: StepFn | None = None,
    result_dir=None,
    **_,
) -> dict[str, Any]:
    """
    TP工模容值测试
    测试步骤:
    1. 进入工模界面
    2. 选择 screen 测试组中的触摸屏自检
    3. 判断是否进入触摸屏自检项
    4. 等待结果并依据标签判定
    5. 关闭工模并返回桌面（失败不影响本项结果）
    预期结果: 触摸屏自检项测试结果为通过（Pass）
    """
    emit(step_update, steps, "[工模容值] 进入屏幕测试组执行触摸屏自检")

    def on_step(label: str, ok: bool) -> None:
        emit(step_update, steps, f"[工模容值] {label}" + ("-成功" if ok else "-失败"))

    # 不传 manual_confirm：由工模界面 Pass/Fail 标签自动判定
    result = run_screen_group_item_test(
        serial,
        SCREEN_TOUCH_SELF_ITEM_KEYWORDS,
        item_label="触摸屏自检",
        result_dir=result_dir,
        on_step=on_step,
    )
    status = result.get("status", "fail")
    message = result.get("message", "触摸屏自检失败")

    on_step("关闭工模应用", close_tranfacmode(serial))
    on_step("返回桌面", go_home(serial))  # 失败不影响判定

    emit(step_update, steps, f"[工模容值]-{'成功' if status == 'pass' else '失败'}")
    return _item("TP工模容值测试", status, message)


TP_TEST_CASES = (
    test_firmware_version,
    test_vendor,
    test_mtk_tpd,
    test_se_nodes,
    test_factory_capacitance,
)


def run_all_test_cases(
    serial: str,
    *,
    step_update: StepFn | None = None,
    result_dir=None,
) -> list[dict[str, Any]]:
    steps = [f"设备: {serial}", "开始执行 TP 流水线适配检查"]
    if callable(step_update):
        step_update("\n".join(steps))
    return [
        fn(serial, steps=steps, step_update=step_update, result_dir=result_dir)
        for fn in TP_TEST_CASES
    ]
