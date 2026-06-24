import importlib.util
import json
import sys
import tempfile
from pathlib import Path

from utils.tdd.apk.call import reset_dial_sequence
from utils.tdd.ui_paths import set_ui_result_dir
from case_catalog import (
    load_case_manual_info,
    make_category_key,
    module_dir,
    parse_category_key,
)
from utils.tdd.ui_automatic import ensure_auxiliary_devices_awake

CASE_ROOT = Path(__file__).resolve().parent
_initialized_modules: set[tuple[str, str]] = set()


def _resolve_module(test_type=None, module=None, category=None):
    if test_type and module:
        return str(test_type).strip(), str(module).strip()
    if category:
        return parse_category_key(str(category))
    raise ValueError("缺少 test_type/module 或 category")


def _ensure_module_init(test_type: str, module: str, device_info=None) -> None:
    key = (test_type, module)
    if key in _initialized_modules:
        return

    init_path = module_dir(test_type, module) / "init.py"
    if init_path.is_file():
        module_name = f"case.{test_type}.{module}.init"
        spec = importlib.util.spec_from_file_location(module_name, init_path)
        if spec is not None and spec.loader is not None:
            init_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(init_module)
            if hasattr(init_module, "run"):
                init_module.run(device_info=device_info)

    _initialized_modules.add(key)


def _load_case_module(test_type: str, module: str, case_index: int):
    folder = module_dir(test_type, module)
    module_path = folder / f"case{case_index}.py"
    if not module_path.is_file():
        return None, f"用例未实现: {test_type}/{module}/case{case_index}.py"

    module_name = f"case.{test_type}.{module}.case{case_index}"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        return None, f"无法加载用例: {test_type}/{module}/case{case_index}.py"

    case_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(case_module)
    return case_module, None


def run(
    category=None,
    case_index=0,
    device_info=None,
    test_type=None,
    module=None,
    **context,
):
    test_type, module = _resolve_module(test_type=test_type, module=module, category=category)
    category = category or make_category_key(test_type, module)

    case_module, _error = _load_case_module(test_type, module, case_index)
    if case_module is None:
        return {"status": "skip", "message": "需人工测试"}

    if not hasattr(case_module, "run"):
        return {"status": "skip", "message": "需人工测试"}

    context = dict(context)
    context["test_type"] = test_type
    context["module"] = module
    context["category"] = category
    context["case_manual_info"] = load_case_manual_info(test_type, module, case_index)

    if device_info is not None:
        context["device_info"] = device_info
        aux_ok, aux_msg = ensure_auxiliary_devices_awake(device_info)
        if not aux_ok:
            return {"status": "fail", "message": aux_msg}

    _ensure_module_init(test_type, module, device_info=context.get("device_info"))
    reset_dial_sequence()

    # 确保 UI 结果目录已设置（CLI 调用时可能未设置）
    try:
        from utils.tdd.ui_paths import get_ui_result_dir
        if get_ui_result_dir() is None:
            result_dir = context.get("result_dir") or tempfile.mkdtemp(prefix="autotest_")
            set_ui_result_dir(result_dir)
    except Exception:
        pass

    # 注入 step_update 回调：通过 stdout 实时输出步骤
    def step_update(steps: str) -> None:
        print(json.dumps({"type": "step", "step": steps}), flush=True)

    context["step_update"] = step_update

    # 注入 manual_confirm 回调：stdout 发消息 → stdin 等回复
    def manual_confirm(message: str) -> str:
        print(json.dumps({"type": "manual_confirm", "message": message}), flush=True)
        response = sys.stdin.readline().strip()
        return response

    context["manual_confirm"] = manual_confirm

    result = case_module.run(case_index=case_index, **context)
    if isinstance(result, str):
        return {"status": result, "message": ""}
    if isinstance(result, dict):
        status = result.get("status", "pass")
        payload = {
            "status": status,
            "message": result.get("message", ""),
            "full_automation": bool(result.get("full_automation", True)),
        }
        if status == "pending":
            payload["full_automation"] = False
        return payload
    return {"status": "pass", "message": "", "full_automation": True}


# CLI 入口：被 Node.js 后端调用时通过命令行参数执行
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="TAHP 用例执行器")
    parser.add_argument("--test-type", required=True, help="测试类型 (str4/week)")
    parser.add_argument("--module", required=True, help="模块名")
    parser.add_argument("--case-index", type=int, required=True, help="用例编号")
    parser.add_argument("--device-info", default="{}", help="设备信息 JSON")
    args = parser.parse_args()

    try:
        device_info = json.loads(args.device_info)
    except json.JSONDecodeError:
        device_info = {}

    result = run(
        test_type=args.test_type,
        module=args.module,
        case_index=args.case_index,
        device_info=device_info,
    )
    print(json.dumps(result, ensure_ascii=False))
