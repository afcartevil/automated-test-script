"""pipeline_adapt / LCM 用例列表（由 case1 顺序编排执行）。"""

from __future__ import annotations

import re
import time
from typing import Any

from _common import StepFn, adb_cat, adb_run, adb_shell, emit, try_adb_root
from utils.tdd.ui_automatic import ensure_screen_on_and_unlocked, get_screen_state

_TRAN_DISPLAY = "/sys/kernel/tran_display"
_LCM_NAME_PATH = f"{_TRAN_DISPLAY}/lcm_name"
_BACKLIGHT_DIR = "/sys/class/leds/lcd-backlight"
_BRIGHTNESS_PATH = f"{_BACKLIGHT_DIR}/brightness"
# 对齐实机 `ls /sys/class/leds/lcd-backlight -lZ`：
# brightness → u:object_r:sysfs_backlight_file:s0
# connector_id / led_type / led_mode → u:object_r:sysfs_leds:s0
_SE_NODES = (
    ("connector_id", ("sysfs_leds",)),
    ("brightness", ("sysfs_backlight_file",)),
    ("led_type", ("sysfs_leds",)),
    ("led_mode", ("sysfs_leds",)),
)
_BACKLIGHT_KW = "lcm_setbacklight_cmdq"
# IC_分辨率_dsi_(cphy)传输模式(dsc)_模组厂_玻璃(Hz)_项目名
# cphy 允许在 vdo/cmd 前或后，兼容 nt36672c_fhdp_dsi_vdo_cphy_90hz_txd
_LCM_NAME_RE = re.compile(
    r"^[A-Za-z0-9]+_[A-Za-z0-9]+_dsi(?:_cphy)?_(?:vdo|cmd)(?:_cphy)?(?:_dsc)?(?:_[A-Za-z0-9]+)+$",
    re.I,
)
_STATUS_SUFFIX = {
    "pass": "成功",
    "fail": "失败",
    "skip": "跳过",
}


def _item(name: str, status: str, message: str) -> dict[str, Any]:
    return {"name": name, "status": status, "message": message}


def _path_exists(serial: str, path: str) -> bool:
    out = adb_shell(serial, f"if [ -e {path} ]; then echo YES; else echo NO; fi")
    return "YES" in (out or "").split()


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
    ret = adb_run(serial, "shell", "dmesg", timeout=20)
    return ((ret.stdout or "") or (ret.stderr or "")).strip()


def _parse_brightness(raw: str) -> int | None:
    lines = (raw or "").strip().splitlines()
    if not lines:
        return None
    token = lines[0].strip().split()[0]
    try:
        return int(token)
    except ValueError:
        return None


def _ko_loaded(serial: str, lcm_name: str) -> tuple[bool, str]:
    lsmod = adb_shell(serial, "lsmod", timeout=20)
    modules = adb_shell(serial, "cat /proc/modules 2>/dev/null", timeout=20)
    sysmod = adb_shell(serial, "ls /sys/module 2>/dev/null", timeout=15)
    blob = f"{lsmod}\n{modules}".lower()
    name = (lcm_name or "").strip().lower()
    ic = name.split("_")[0] if name else ""
    if name and name in blob:
        return True, f"lsmod/modules 匹配 {lcm_name}"
    if len(ic) >= 4 and ic in blob:
        return True, f"lsmod/modules 匹配 IC {ic}"
    sys_names = {n.strip().lower() for n in (sysmod or "").split() if n.strip()}
    if name.replace("-", "_") in sys_names:
        return True, f"/sys/module 存在 {lcm_name}"
    if len(ic) >= 4 and ic.replace("-", "_") in sys_names:
        return True, f"/sys/module 存在 {ic}"
    preview = (lsmod or sysmod or "<空>")[:400].replace("\n", " | ")
    return False, f"lsmod 未匹配 {lcm_name}（屏幕连接失败或 KO 未加载）; 摘要: {preview}"


def test_screen_load(serial: str, *, steps: list[str], step_update: StepFn | None = None, **_) -> dict[str, Any]:
    """
    屏幕加载是否成功检查
    测试步骤:
    1. 确认 /sys/kernel/tran_display 节点存在
    2. cat /sys/kernel/tran_display/lcm_name
    3. lsmod 匹配屏幕名，确认 KO 加载
    预期结果: 节点存在；lcm_name 符合 IC_分辨率_dsi_(cphy)传输模式(dsc)_模组厂_玻璃(Hz)_项目名
    """
    name = "屏幕加载是否成功检查"
    emit(step_update, steps, f"[{name}] 检查 {_TRAN_DISPLAY}")
    if not _path_exists(serial, _TRAN_DISPLAY):
        emit(step_update, steps, f"[{name}]-失败")
        return _item(name, "fail", f"节点不存在: {_TRAN_DISPLAY}（屏幕连接失败或 KO 未加载）")
    emit(step_update, steps, f"[{name}] 节点存在")

    emit(step_update, steps, f"[{name}] 读取 {_LCM_NAME_PATH}")
    actual = adb_cat(serial, _LCM_NAME_PATH).strip()
    lcm_name = (actual.splitlines()[0] if actual else "").strip()
    emit(step_update, steps, f"[{name}] lcm_name: {lcm_name or '<空>'}")
    if not lcm_name:
        emit(step_update, steps, f"[{name}]-失败")
        return _item(name, "fail", "lcm_name 为空（屏幕连接失败或 KO 未加载）")
    if not _LCM_NAME_RE.match(lcm_name):
        emit(step_update, steps, f"[{name}]-失败")
        return _item(
            name,
            "fail",
            f"格式校验失败: expected IC_分辨率_dsi_(cphy)vdo|cmd(dsc)_模组厂_玻璃(Hz)_项目名; actual: {lcm_name}",
        )

    emit(step_update, steps, f"[{name}] lsmod 匹配 {lcm_name}")
    loaded, ko_msg = _ko_loaded(serial, lcm_name)
    emit(step_update, steps, f"[{name}] {ko_msg}")
    if not loaded:
        emit(step_update, steps, f"[{name}]-失败")
        return _item(name, "fail", ko_msg)
    emit(step_update, steps, f"[{name}]-成功")
    return _item(name, "pass", f"{lcm_name}; {ko_msg}")


def test_screen_light(serial: str, *, steps: list[str], step_update: StepFn | None = None, **_) -> dict[str, Any]:
    """
    屏幕是否正常点亮
    测试步骤:
    1. dmesg -C 清除日志
    2. input keyevent 26 切换电源（先确保亮屏，第一次为灭屏）
    3. 检索 dmesg 是否出现 lcm_setbacklight_cmdq
    4. cat brightness（期望 0）
    5. 再次 keyevent 26（亮屏）
    6. 再读 brightness（期望非 0）
    预期结果: 无 lcm_setbacklight_cmdq 则屏幕未连接；灭屏 0、亮屏非 0 为正常
    """
    name = "屏幕是否正常点亮"
    emit(step_update, steps, f"[{name}] 尝试 adb root（dmesg -C 需要）")
    root_ok, root_msg = try_adb_root(serial)
    emit(step_update, steps, f"[{name}] adb root: {root_msg or ('ok' if root_ok else '失败')}")

    emit(step_update, steps, f"[{name}] 先确保亮屏，使第一次 keyevent 26 为灭屏")
    if not ensure_screen_on_and_unlocked(serial):
        emit(step_update, steps, f"[{name}]-失败")
        return _item(name, "fail", "亮屏解锁失败，无法执行开关屏检查")
    emit(step_update, steps, f"[{name}] 当前屏幕: {get_screen_state(serial)}")

    emit(step_update, steps, f"[{name}] dmesg -C 清除日志")
    cleared, clear_msg = _dmesg_clear(serial)
    if not cleared:
        emit(step_update, steps, f"[{name}] 清除日志失败: {clear_msg}")
        return _item(name, "fail", f"dmesg -C 失败: {clear_msg}")
    emit(step_update, steps, f"[{name}] 清除日志-成功")

    emit(step_update, steps, f"[{name}] input keyevent 26（灭屏）")
    adb_run(serial, "shell", "input", "keyevent", "26", timeout=10)
    time.sleep(2.0)
    off_raw = adb_cat(serial, _BRIGHTNESS_PATH)
    off_val = _parse_brightness(off_raw)
    emit(step_update, steps, f"[{name}] 灭屏 brightness={off_raw.strip() or '<空>'} 屏幕={get_screen_state(serial)}")

    emit(step_update, steps, f"[{name}] input keyevent 26（亮屏）")
    adb_run(serial, "shell", "input", "keyevent", "26", timeout=10)
    time.sleep(2.0)
    on_raw = adb_cat(serial, _BRIGHTNESS_PATH)
    on_val = _parse_brightness(on_raw)
    emit(step_update, steps, f"[{name}] 亮屏 brightness={on_raw.strip() or '<空>'} 屏幕={get_screen_state(serial)}")

    log = _dmesg_raw(serial)
    has_kw = _BACKLIGHT_KW.lower() in (log or "").lower()
    kw_lines = [ln for ln in (log or "").splitlines() if _BACKLIGHT_KW.lower() in ln.lower()]
    preview = " | ".join(kw_lines[-5:]) if kw_lines else "<无>"
    emit(step_update, steps, f"[{name}] dmesg {_BACKLIGHT_KW}: {preview}")

    if not has_kw:
        emit(step_update, steps, f"[{name}]-失败")
        return _item(name, "fail", f"dmesg 无 {_BACKLIGHT_KW}，屏幕未成功连接")
    if off_val is None:
        emit(step_update, steps, f"[{name}]-失败")
        return _item(name, "fail", f"灭屏后无法读取 brightness: {off_raw or '<空>'}")
    if on_val is None:
        emit(step_update, steps, f"[{name}]-失败")
        return _item(name, "fail", f"亮屏后无法读取 brightness: {on_raw or '<空>'}")
    if off_val != 0 or on_val == 0:
        emit(step_update, steps, f"[{name}]-失败")
        return _item(
            name,
            "fail",
            f"背光切换异常: 灭屏 brightness={off_val}（期望 0），亮屏 brightness={on_val}（期望非 0）",
        )
    emit(step_update, steps, f"[{name}]-成功")
    return _item(name, "pass", f"灭屏 brightness=0，亮屏 brightness={on_val}，dmesg 含 {_BACKLIGHT_KW}")


def _selinux_label(ls_out: str) -> str:
    m = re.search(r"(u:object_r:[^\s]+)", ls_out or "")
    if m:
        return m.group(1)
    m = re.search(r"(u:[^\s]+)", ls_out or "")
    if m:
        return m.group(1)
    parts = (ls_out or "").split()
    return parts[0] if parts else "(unknown)"


def test_se_nodes(serial: str, *, steps: list[str], step_update: StepFn | None = None, **_) -> dict[str, Any]:
    """
    SE节点权限检查
    测试步骤: 检查 /sys/class/leds/lcd-backlight 下节点是否存在、标签是否正确
    检查节点: connector_id、brightness、led_type、led_mode
    预期标签: brightness=sysfs_backlight_file；其余=sysfs_leds；输出均非空
    前置: adb root 成功；失败则 skip 本项
    """
    name = "SE节点权限检查"
    emit(step_update, steps, f"[{name}] 尝试 adb root")
    root_ok, root_msg = try_adb_root(serial)
    if not root_ok:
        emit(step_update, steps, f"[{name}] adb root 失败，跳过: {root_msg}")
        return _item(name, "skip", f"adb root 失败，跳过 SE 节点检查: {root_msg}")
    emit(step_update, steps, f"[{name}] adb root 成功: {root_msg or 'ok'}")
    emit(step_update, steps, f"[{name}] 检查 {_BACKLIGHT_DIR} 节点存在性、SELinux 标签与输出")

    if not _path_exists(serial, _BACKLIGHT_DIR):
        emit(step_update, steps, f"[{name}]-失败")
        return _item(name, "fail", f"目录不存在: {_BACKLIGHT_DIR}")

    dir_ls = adb_shell(serial, f"ls -lZ {_BACKLIGHT_DIR} 2>&1")
    emit(step_update, steps, f"[{name}] ls -lZ {_BACKLIGHT_DIR}:\n{dir_ls or '<空>'}")

    fail = False
    buckets: dict[str, list[str]] = {
        "不存在": [],
        "标签未打标": [],
        "标签类型错误": [],
        "读权限失败": [],
        "输出为空": [],
    }

    for node, frags in _SE_NODES:
        path = f"{_BACKLIGHT_DIR}/{node}"
        expect = "/".join(frags)
        ls_out = adb_shell(serial, f"ls -lZ {path} 2>&1")
        low = (ls_out or "").lower()
        if "no such file" in low or not ls_out:
            buckets["不存在"].append(path)
            fail = True
            emit(step_update, steps, f"[{name}] {path}: MISSING")
            continue

        label = _selinux_label(ls_out)
        match = "OK"
        if re.search(r"unlabeled|default_t", label):
            match, fail = "FAIL-label", True
            buckets["标签未打标"].append(f"{path}({label})")
        elif not any(f in label for f in frags):
            match, fail = "FAIL-type", True
            buckets["标签类型错误"].append(f"{path}({label}, expect {expect})")

        cat_out = adb_shell(serial, f"cat {path} 2>&1")
        cat_low = (cat_out or "").lower()
        read_st = "OK"
        value = (cat_out or "").strip()
        if "permission denied" in cat_low:
            read_st, match, fail = "DENIED", "FAIL-read", True
            buckets["读权限失败"].append(path)
        elif "no such file" in cat_low:
            read_st, match, fail = "MISSING", "FAIL-read", True
            buckets["不存在"].append(path)
        elif not value:
            read_st, match, fail = "EMPTY", "FAIL-empty", True
            buckets["输出为空"].append(path)

        emit(
            step_update,
            steps,
            f"[{name}] {path}: label={label} expect={expect} read={read_st} value={value or '<空>'} {match}",
        )

    detail_parts = [f"{k}:\n" + "\n".join(v) for k, v in buckets.items() if v]
    detail = "\n".join(detail_parts) if detail_parts else "全部正常"
    if fail:
        emit(step_update, steps, f"[{name}]-失败:\n{detail}")
        return _item(name, "fail", detail)
    emit(step_update, steps, f"[{name}]-成功:\n{detail}")
    return _item(name, "pass", "标签符合 sysfs_backlight_file/sysfs_leds，输出均非空")


LCM_TEST_CASES = (
    test_screen_load,
    test_screen_light,
    test_se_nodes,
)


def run_all_test_cases(
    serial: str,
    *,
    step_update: StepFn | None = None,
    result_dir=None,
) -> tuple[list[dict[str, Any]], list[str]]:
    steps = [f"设备: {serial}", "开始执行 LCM 流水线适配检查"]
    if callable(step_update):
        step_update("\n".join(steps))

    results: list[dict[str, Any]] = []
    for fn in LCM_TEST_CASES:
        result = fn(serial, steps=steps, step_update=step_update, result_dir=result_dir)
        results.append(result)
        suffix = _STATUS_SUFFIX.get(str(result.get("status")), str(result.get("status")))
        emit(step_update, steps, f"{result.get('name')}-{suffix}")
    return results, steps
