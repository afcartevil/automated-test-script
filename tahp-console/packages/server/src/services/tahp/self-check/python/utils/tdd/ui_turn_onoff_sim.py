"""SIM 详情页「启用卡*」开关：打开或关闭。"""

from utils.tdd.ui_switch import EnableTarget, set_labeled_switch_enable


def _is_enable_row_label(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if any(
        x in t
        for x in ("首选网络", "漫游", "APN", "网络运营商", "VoLTE", "视频通话", "4G通话")
    ):
        return False
    if t.startswith("启用卡") or t.startswith("Enable card"):
        return True
    if t in ("Enable SIM", "启用 SIM"):
        return True
    return False


def set_sim_enable(device_id: str, enable: EnableTarget) -> bool:
    """
    在当前 SIM 详情页切换「启用卡*」开关至目标状态。

    参数:
        device_id: 设备 adb 序列号
        enable: True/打开 或 False/关闭（也支持 1/0、「打开」「关闭」等）

    返回:
        最终状态符合目标为 True，否则 False。
    """
    return set_labeled_switch_enable(device_id, enable, _is_enable_row_label)
