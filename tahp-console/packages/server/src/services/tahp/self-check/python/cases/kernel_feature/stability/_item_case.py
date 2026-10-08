"""Shared runner for kernel_feature/stability caseN.py (one checklist item each)."""
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


def _checker_config(device_info: dict) -> dict:
    """从 device_info 透传可选配置（也可走 env / stability.config.json）。

    Console 会注入 work_dir=会话 case-workdir/<caseKey>，产物落在用例执行目录。
    """
    if not isinstance(device_info, dict):
        return {}
    cfg = {}
    for key in ("code_dir", "tools_root", "work_dir", "product_name", "case2_reboot"):
        if device_info.get(key) not in (None, ""):
            cfg[key] = device_info[key]
    # 兼容嵌套
    nested = device_info.get("stability") or device_info.get("kernel_feature") or {}
    if isinstance(nested, dict):
        for key in ("code_dir", "tools_root", "work_dir", "product_name", "case2_reboot"):
            if nested.get(key) not in (None, "") and key not in cfg:
                cfg[key] = nested[key]
    # resultDir 兜底：未显式传 work_dir 时拼 case 子目录
    if not cfg.get("work_dir"):
        result_dir = device_info.get("resultDir") or device_info.get("result_dir")
        if result_dir:
            cfg["work_dir"] = str(Path(result_dir) / "case-workdir" / "stability")
    return cfg


def _load_checker_class():
    script = (
        Path(__file__).resolve().parents[3]
        / "tools"
        / "stability_checker"
        / "stability_checker.py"
    )
    if not script.is_file():
        raise FileNotFoundError(f"stability checker 不存在: {script}")
    spec = importlib.util.spec_from_file_location("stability_checker_tool", script)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载 stability checker: {script}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.StabilityChecker, module.checklist_item_name, len(module.CHECKLIST_ITEMS)


def run_checklist_item(item_id: int, device_info=None, step_update=None, **_context):
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
        StabilityChecker, checklist_item_name, total = _load_checker_class()
    except Exception as exc:
        add_step(f"加载 stability checker 失败: {exc}")
        return {"status": "fail", "message": str(exc), "full_automation": True}

    name = checklist_item_name(item_id)
    cfg = _checker_config(info if isinstance(info, dict) else {})
    work = cfg.get("work_dir")
    add_step(f"执行稳定性检查项 {item_id}/{total}：{name}（设备 {serial}）")
    if work:
        add_step(f"用例工作目录: {work}")
    checker = StabilityChecker(
        serial=serial,
        on_step=add_step,
        config=cfg,
    )
    result = checker.run_item(item_id)
    status = str(result.get("status") or "").lower()
    detail = str(result.get("info") or "")
    message = f"{name}: {detail}" if detail else name

    if status == "pass":
        add_step(f"通过 — {message}")
        return {"status": "pass", "message": message, "full_automation": True}
    if status == "na":
        add_step(f"NA — {message}")
        return {"status": "na", "message": message, "full_automation": True}
    if status == "pending":
        add_step(f"待确认 — {message}")
        return {"status": "pending", "message": message, "full_automation": False}

    add_step(f"失败 — {message}")
    return {"status": "fail", "message": message, "full_automation": True}
