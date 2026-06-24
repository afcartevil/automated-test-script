"""检查数据切换-移动网络设置：复用 case5 三个子步骤结果。"""

from case.case_catalog import resolve_result_category
from test.case_reuse import case_name
from test.result_copy import get_sub_step_result_from_context

SOURCE_CASE_INDEX = 5

REUSED_SUB_STEP_LABELS = (
    "调起APK访问百度(卡1数据，应能访问)",
    "调起APK访问百度(卡2数据，应能访问)",
    "进入SIM卡与网络设置，检查上网卡菜单应不置灰",
)


def run(category=None, case_index=None, device_info=None, **context):
    del case_index, device_info
    step_update = context.get("step_update")
    category_key = resolve_result_category(category, context=context)
    case5_name = case_name(category_key, SOURCE_CASE_INDEX, context=context)

    sub_steps = ""
    outcomes: list[str] = []

    def update(steps: str):
        if callable(step_update):
            step_update(steps)

    for label in REUSED_SUB_STEP_LABELS:
        sub_steps += f"\n复用case{SOURCE_CASE_INDEX}「{label}」"
        update(sub_steps)

        outcome = get_sub_step_result_from_context(
            context,
            category_key,
            SOURCE_CASE_INDEX,
            label,
        )
        outcomes.append(outcome)

        if not outcome:
            sub_steps += "-跳过(未读到)"
            update(sub_steps)
            continue
        if outcome == "成功":
            sub_steps += "-成功"
        else:
            sub_steps += "-失败"
        update(sub_steps)

    if any(not o for o in outcomes):
        return {
            "status": "skip",
            "message": f"请勾选{case5_name}",
        }

    if any(o == "失败" for o in outcomes):
        return {
            "status": "fail",
            "message": "复用case5结果",
        }

    return {
        "status": "pass",
        "message": "复用case5结果",
    }
