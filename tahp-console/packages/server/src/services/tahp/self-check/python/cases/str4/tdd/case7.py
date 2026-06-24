"""检查数据开关-SIM卡与网络设置：复用 case5 百度访问（卡1数据）子步骤结果。"""

from case.case_catalog import resolve_result_category
from test.case_reuse import case_name
from test.result_copy import get_sub_step_result_from_context

SOURCE_CASE_INDEX = 5
SOURCE_SUB_STEP_LABEL = "调起APK访问百度(卡1数据，应能访问)"


def run(category=None, case_index=None, device_info=None, **context):
    del case_index, device_info
    step_update = context.get("step_update")
    category_key = resolve_result_category(category, context=context)
    case5_name = case_name(category_key, SOURCE_CASE_INDEX, context=context)

    sub_steps = ""

    def update(steps: str):
        if callable(step_update):
            step_update(steps)

    sub_steps += (
        f"\n复用case{SOURCE_CASE_INDEX}子步骤「{SOURCE_SUB_STEP_LABEL}」"
    )
    update(sub_steps)

    outcome = get_sub_step_result_from_context(
        context,
        category_key,
        SOURCE_CASE_INDEX,
        SOURCE_SUB_STEP_LABEL,
    )

    if outcome == "成功":
        sub_steps += "-成功"
        update(sub_steps)
        return {
            "status": "pass",
            "message": f"复用case{SOURCE_CASE_INDEX}百度访问结果",
        }

    if outcome == "失败":
        sub_steps += "-失败"
        update(sub_steps)
        return {
            "status": "fail",
            "message": f"复用case{SOURCE_CASE_INDEX}百度访问结果",
        }

    sub_steps += "-跳过(未读到)"
    update(sub_steps)
    return {
        "status": "skip",
        "message": f"请勾选{case5_name}",
    }
