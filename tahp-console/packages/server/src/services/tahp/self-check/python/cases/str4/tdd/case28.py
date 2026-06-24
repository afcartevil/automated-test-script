"""检查UE双卡LTE蜂窝热点功能：复用 case27 结果。"""
from test.case_reuse import run_reuse_whole_case


def run(category=None, case_index=None, device_info=None, **context):
    del category, case_index
    return run_reuse_whole_case(27, device_info=device_info, **context)
