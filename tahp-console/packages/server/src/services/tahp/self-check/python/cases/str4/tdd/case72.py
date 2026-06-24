"""检查UE双卡SA手动驻网功能：复用 case3 结果。"""
from test.case_reuse import run_reuse_whole_case


def run(category=None, case_index=None, device_info=None, **context):
    del category, case_index
    return run_reuse_whole_case(3, device_info=device_info, **context)
