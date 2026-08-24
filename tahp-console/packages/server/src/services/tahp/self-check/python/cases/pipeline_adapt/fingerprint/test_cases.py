"""pipeline_adapt / 指纹+人脸用例列表（由 case1 顺序编排执行）。"""

from __future__ import annotations

from typing import Any

from _common import StepFn, adb_cat, adb_run, adb_shell, emit

_TRAN_KEYS = '"tran-keys"'
_FP_HAL = "android.hardware.biometrics.fingerp"
_FACE_HAL = "android.hardware.biometrics.face"
_VENDOR_PATH = "/sys/kernel/tran_fp/vendor_name"
_IC_PATH = "/sys/kernel/tran_fp/ic_name"
_STATUS_SUFFIX = {
    "pass": "成功",
    "fail": "失败",
    "skip": "跳过",
}


def _item(name: str, status: str, message: str) -> dict[str, Any]:
    return {"name": name, "status": status, "message": message}


def _preview(blob: str, *, limit: int = 400) -> str:
    text = (blob or "").strip() or "<空>"
    return text[:limit].replace("\n", " | ")


def _match_lines(blob: str, needle: str) -> list[str]:
    return [ln.strip() for ln in (blob or "").splitlines() if needle in ln]


def test_fp_input_device(serial: str, *, steps: list[str], step_update: StepFn | None = None, **_) -> dict[str, Any]:
    """
    指纹输入设备检查
    测试步骤: getevent -li（list 设备；不用 -ltr，避免实时监听卡住）
    预期结果: 输出包含 name: "tran-keys"
    """
    name = "指纹输入设备检查"
    emit(step_update, steps, f"[{name}] 执行 getevent -li")
    actual = adb_shell(serial, "getevent -li", timeout=45)
    emit(step_update, steps, f"[{name}] 输出摘要: {_preview(actual)}")
    if _TRAN_KEYS not in (actual or ""):
        emit(step_update, steps, f"[{name}]-失败")
        return _item(name, "fail", f"expected contains name: {_TRAN_KEYS}")
    hit = _match_lines(actual, "tran-keys")
    emit(step_update, steps, f"[{name}]-成功")
    return _item(name, "pass", hit[0] if hit else f"getevent 含 name: {_TRAN_KEYS}")


def test_fp_service(serial: str, *, steps: list[str], step_update: StepFn | None = None, **_) -> dict[str, Any]:
    """
    指纹服务检查
    测试步骤: ps -A（本机检索 fingerprint，避免 adb 管道在 Windows 被拆参）
    预期结果: 输出包含 android.hardware.biometrics.fingerp
    """
    name = "指纹服务检查"
    emit(step_update, steps, f"[{name}] 执行 ps -A")
    ret = adb_run(serial, "shell", "ps", "-A", timeout=20)
    actual = ((ret.stdout or "") or (ret.stderr or "")).strip()
    hits = _match_lines(actual, _FP_HAL)
    emit(step_update, steps, f"[{name}] 匹配行: {_preview(chr(10).join(hits) if hits else actual)}")
    if not hits:
        emit(step_update, steps, f"[{name}]-失败")
        return _item(name, "fail", f"expected contains: {_FP_HAL}")
    emit(step_update, steps, f"[{name}]-成功")
    return _item(name, "pass", hits[0])


def test_fp_vendor_name(serial: str, *, steps: list[str], step_update: StepFn | None = None, **_) -> dict[str, Any]:
    """
    供应商 name 检查
    测试步骤: cat /sys/kernel/tran_fp/vendor_name
    预期结果: 有输出
    """
    name = "供应商name检查"
    emit(step_update, steps, f"[{name}] 读取 {_VENDOR_PATH}")
    actual = adb_cat(serial, _VENDOR_PATH).strip()
    emit(step_update, steps, f"[{name}] 输出: {actual or '<空>'}")
    if not actual:
        emit(step_update, steps, f"[{name}]-失败")
        return _item(name, "fail", f"{_VENDOR_PATH} 无输出")
    emit(step_update, steps, f"[{name}]-成功")
    return _item(name, "pass", actual.splitlines()[0].strip())


def test_fp_ic_name(serial: str, *, steps: list[str], step_update: StepFn | None = None, **_) -> dict[str, Any]:
    """
    指纹 IC 检查
    测试步骤: cat /sys/kernel/tran_fp/ic_name
    预期结果: 有输出
    """
    name = "指纹IC检查"
    emit(step_update, steps, f"[{name}] 读取 {_IC_PATH}")
    actual = adb_cat(serial, _IC_PATH).strip()
    emit(step_update, steps, f"[{name}] 输出: {actual or '<空>'}")
    if not actual:
        emit(step_update, steps, f"[{name}]-失败")
        return _item(name, "fail", f"{_IC_PATH} 无输出")
    emit(step_update, steps, f"[{name}]-成功")
    return _item(name, "pass", actual.splitlines()[0].strip())


def test_face_service(serial: str, *, steps: list[str], step_update: StepFn | None = None, **_) -> dict[str, Any]:
    """
    人脸服务检查
    测试步骤: ps -A（本机检索 face）
    预期结果: 输出包含 android.hardware.biometrics.face
    """
    name = "人脸服务检查"
    emit(step_update, steps, f"[{name}] 执行 ps -A")
    ret = adb_run(serial, "shell", "ps", "-A", timeout=20)
    actual = ((ret.stdout or "") or (ret.stderr or "")).strip()
    hits = _match_lines(actual, _FACE_HAL)
    emit(step_update, steps, f"[{name}] 匹配行: {_preview(chr(10).join(hits) if hits else actual)}")
    if not hits:
        emit(step_update, steps, f"[{name}]-失败")
        return _item(name, "fail", f"expected contains: {_FACE_HAL}")
    emit(step_update, steps, f"[{name}]-成功")
    return _item(name, "pass", hits[0])


FP_TEST_CASES = (
    test_fp_input_device,
    test_fp_service,
    test_fp_vendor_name,
    test_fp_ic_name,
    test_face_service,
)


def run_all_test_cases(
    serial: str,
    *,
    step_update: StepFn | None = None,
    result_dir=None,
) -> tuple[list[dict[str, Any]], list[str]]:
    steps = [f"设备: {serial}", "开始执行 指纹/人脸 流水线适配检查"]
    if callable(step_update):
        step_update("\n".join(steps))

    results: list[dict[str, Any]] = []
    for fn in FP_TEST_CASES:
        result = fn(serial, steps=steps, step_update=step_update, result_dir=result_dir)
        results.append(result)
        suffix = _STATUS_SUFFIX.get(str(result.get("status")), str(result.get("status")))
        emit(step_update, steps, f"{result.get('name')}-{suffix}")
    return results, steps
