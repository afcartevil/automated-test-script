"""SIM 详情页「VoLTE/4G通话」开关：打开或关闭。"""

from utils.tdd.ui_switch import EnableTarget, set_labeled_switch_enable

__all__ = ["EnableTarget", "set_volte_enable"]


def _is_volte_row_label(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if "启用卡" in t or t.lower().startswith("enable card"):
        return False
    low = t.lower().replace(" ", "")
    if "volte" in low:
        return True
    if "4g通话" in low or "4gcalling" in low:
        return True
    return False


def set_volte_enable(device_id: str, enable: EnableTarget) -> bool:
    """
    在当前 SIM 详情页切换「VoLTE/4G通话」开关至目标状态。

    参数:
        device_id: 设备 adb 序列号
        enable: True/打开 或 False/关闭（也支持 1/0、「打开」「关闭」等）

    返回:
        最终状态符合目标为 True，否则 False。
    """
    return set_labeled_switch_enable(device_id, enable, _is_volte_row_label)
