from __future__ import annotations

import importlib.util
from pathlib import Path


def _device_serial(device_info: dict) -> str:
    dut = device_info.get("DUT") if isinstance(device_info, dict) else None
    if isinstance(dut, list) and dut:
        serial = dut[0].get("device_id") or dut[0].get("deviceId")
        if serial:
            return str(serial)
    if isinstance(device_info, dict):
        serial = device_info.get("deviceId") or device_info.get("device_id")
        if serial:
            return str(serial)
    raise ValueError("缺少测试机设备序列号")


def _load_checker_class():
    script = (
        Path(__file__).resolve().parents[3]
        / "tools"
        / "p1_checker"
        / "p1_checker.py"
    )
    if not script.is_file():
        raise FileNotFoundError(f"P1 checker 不存在: {script}")
    spec = importlib.util.spec_from_file_location("p1_checker_tool", script)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载 P1 checker: {script}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.P1Checker


def run(device_info=None, step_update=None, gesture_state="全闭", **_context):
    info = device_info or {}
    try:
        serial = _device_serial(info)
    except ValueError as exc:
        return {"status": "fail", "message": str(exc), "full_automation": True}

    steps: list[str] = []

    def add_step(text: str) -> None:
        steps.append(text)
        if step_update:
            step_update("\n".join(steps))

    try:
        P1Checker = _load_checker_class()
    except Exception as exc:
        add_step(f"加载 P1 checker 失败: {exc}")
        return {"status": "fail", "message": str(exc), "full_automation": True}

    add_step(f"准备执行 P1 驱动自检，设备: {serial}，手势状态: {gesture_state}")
    checker = P1Checker(serial=serial, on_step=add_step)
    result = checker.run_all(gesture_state=gesture_state)

    if result.get("error") and not result.get("items"):
        add_step(f"设备检查失败: {result['error']}")
        return {
            "status": "fail",
            "message": str(result["error"]),
            "full_automation": True,
        }

    total = int(result.get("total") or 0)
    passed = int(result.get("passed") or 0)
    failed = int(result.get("failed") or 0)
    blocked = int(result.get("blocked") or 0)
    blocked_items = [
        item for item in (result.get("items") or [])
        if str(item.get("status", "")).lower() == "blocked"
    ]
    failed_items = [
        f"{item.get('name')}: {item.get('actual')}"
        for item in (result.get("items") or [])
        if str(item.get("status", "")).lower() == "fail"
    ]

    summary = f"{passed} 通过 / {failed} 失败 / {blocked} Blocked / 共 {total} 项"
    xlsx_path = result.get("xlsx_path", "")

    if failed == 0 and total > 0:
        add_step(f"P1 驱动自检通过 — {summary}")
        if xlsx_path:
            add_step(f"报告: {xlsx_path}")
        # 收集所有检查项的 evidence 数据
        all_evidence = []
        all_detail = {}
        for item in (result.get("items") or []):
            if item.get("evidence"):
                all_evidence.extend(item["evidence"])
            if item.get("detail"):
                item_name = item.get("name", "unknown")
                all_detail[item_name] = item["detail"]
        return {
            "status": "pass",
            "message": summary,
            "full_automation": True,
            "evidence": all_evidence if all_evidence else None,
            "detail": all_detail if all_detail else None,
        }

    detail = "; ".join(failed_items[:8])
    if blocked_items:
        blocked_names = [f"{i.get('name')}: {i.get('actual')}" for i in blocked_items]
        if detail:
            detail += "; "
        detail += f"Blocked: {'; '.join(blocked_names)}"
    if len(failed_items) > 8:
        detail += f" …等共 {len(failed_items)} 项失败"
    message = f"{summary}" + (f"；失败项: {detail}" if detail else "")
    if xlsx_path:
        message += f"；报告: {xlsx_path}"
    add_step(f"P1 驱动自检失败 — {message}")
    
    # 收集所有检查项的 evidence 数据
    all_evidence = []
    all_detail = {}
    for item in (result.get("items") or []):
        if item.get("evidence"):
            all_evidence.extend(item["evidence"])
        if item.get("detail"):
            item_name = item.get("name", "unknown")
            all_detail[item_name] = item["detail"]
    
    return {
        "status": "fail",
        "message": message,
        "full_automation": True,
        "evidence": all_evidence if all_evidence else None,
        "detail": all_detail if all_detail else None,
    }
