"""检查5G NSA语音通话功能（主被叫）：复用 case22 5G自动时拨打电话子步骤结果。"""

from case.case_catalog import resolve_result_category
from test.case_reuse import case_name
from test.result_copy import get_sub_step_result_from_context

SOURCE_CASE_INDEX = 22
NETWORK_LABEL = "2G/3G/4G/5G自动"

# 与 case22.py NETWORK_PHASES 首档网络下语音主被叫子步骤名称一致
REUSED_SUB_STEP_LABELS = (
    f"测试机主叫辅测机语音({NETWORK_LABEL})",
    f"辅测机主叫测试机语音({NETWORK_LABEL})",
)


def run(category=None, case_index=None, device_info=None, **context):
    del case_index, device_info
    step_update = context.get("step_update")
    category_key = resolve_result_category(category, context=context)
    source_case_name = case_name(category_key, SOURCE_CASE_INDEX, context=context)

    sub_steps = ""
    outcomes: list[str] = []

    def update(steps: str):
        if callable(step_update):
            step_update(steps)

    for label in REUSED_SUB_STEP_LABELS:
        sub_steps += f"\n复用case{SOURCE_CASE_INDEX}「{label}」"
        update(sub_steps)

        outcome = get_sub_step_result_from_context(
            context, category_key, SOURCE_CASE_INDEX, label
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
            "message": f"请勾选{source_case_name}",
        }

    if any(o == "失败" for o in outcomes):
        return {
            "status": "fail",
            "message": "复用case22 5G自动拨打电话结果",
        }

    return {
        "status": "pass",
        "message": "复用case22 5G自动拨打电话结果",
    }
