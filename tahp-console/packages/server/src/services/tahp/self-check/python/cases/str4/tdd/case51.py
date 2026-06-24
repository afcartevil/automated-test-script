"""检查4G网络下国际通用ECC list遍历：复用 case1 拨打ECC子步骤结果。"""
from case.case_catalog import resolve_result_category
from test.case_reuse import case_name
from test.result_copy import get_sub_step_result_from_context

SOURCE_CASE_INDEX = 1
SOURCE_SUB_STEP_LABEL = "拨打紧急号码112"


def run(category=None, case_index=None, device_info=None, **context):
    del case_index, device_info
    step_update = context.get("step_update")
    category_key = resolve_result_category(category, context=context)
    source_case_name = case_name(category_key, SOURCE_CASE_INDEX, context=context)

    sub_steps = (
        f"\n复用case{SOURCE_CASE_INDEX}子步骤「{SOURCE_SUB_STEP_LABEL}」"
    )
    if callable(step_update):
        step_update(sub_steps)

    outcome = get_sub_step_result_from_context(
        context, category_key, SOURCE_CASE_INDEX, SOURCE_SUB_STEP_LABEL
    )
    if outcome == "成功":
        sub_steps += "-成功"
        if callable(step_update):
            step_update(sub_steps)
        return {"status": "pass", "message": "复用case1拨打ECC结果"}

    if outcome == "失败":
        sub_steps += "-失败"
        if callable(step_update):
            step_update(sub_steps)
        return {"status": "NA", "message": "无网络环境"}

    sub_steps += "-跳过(未读到case1该子步骤结果)"
    if callable(step_update):
        step_update(sub_steps)
    return {"status": "skip", "message": f"请勾选{source_case_name}"}
