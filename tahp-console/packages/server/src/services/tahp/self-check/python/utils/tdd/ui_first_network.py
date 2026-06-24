"""SIM 详情页「首选网络类型」设置。"""

import time
from typing import Callable

from utils.tdd.ui_automatic import (
    click_by_match_keywords,
    DEFAULT_MAX_SCROLLS,
    dialog_has_matching_row,
    pred_23g_auto_row,
    pred_2g_only_row,
    pred_3g_only_row,
    pred_5g_auto_row,
    pred_lte234_auto_row,
    select_dialog_row_and_confirm,
)

PREF_NETWORK_ENTRY_KEYWORDS = ("首选网络类型", "首选网络")
SIM_PAGE_SETTLE_SECONDS = 1.0
DIALOG_OPEN_DELAY = 0.9
# 首选网络弹框为短列表，滑动会关闭弹框；仅看当前屏，不滚动
PREF_NETWORK_DIALOG_MAX_SCROLLS = 0

_NETWORK_TYPE_PREDICATES: dict[int, Callable[[str], bool]] = {
    5: pred_5g_auto_row,
    4: pred_lte234_auto_row,
    3: pred_23g_auto_row,
    2: pred_3g_only_row,
    1: pred_2g_only_row,
}


def _open_pref_network_dialog(device_id: str) -> bool:
    if not click_by_match_keywords(
        device_id,
        PREF_NETWORK_ENTRY_KEYWORDS,
        prefer_cached_ui=False,
        max_scrolls=DEFAULT_MAX_SCROLLS,
    ):
        return False
    if DIALOG_OPEN_DELAY > 0:
        time.sleep(DIALOG_OPEN_DELAY)
    return True


def _select_network_mode(
    device_id: str,
    row_pred: Callable[[str], bool],
    *,
    max_scrolls: int = 3,
) -> bool:
    return select_dialog_row_and_confirm(device_id, row_pred, max_scrolls=max_scrolls)


def set_preferred_network(device_id: str, network_type: int) -> bool:
    """
    在 SIM 详情页设置「首选网络类型」。

    调用方需先进入 SIM 卡子界面，本函数会等待页面稳定后再查找并点击「首选网络类型」。

    参数:
        device_id: 设备 adb 序列号
        network_type: 网络模式
            5 — 优先 2G/3G/4G/5G 自动；当前屏无 5G 项（4G 机）不滑动弹框，直接选 2G/3G/4G 自动
            4 — 2G/3G/4G 自动选择
            3 — 2G/3G 自动选择
            2 — 仅 3G
            1 — 仅 2G

    返回:
        成功 True，失败 False。
    """
    if not device_id:
        return False

    try:
        network_type = int(network_type)
    except (TypeError, ValueError):
        return False

    if network_type not in _NETWORK_TYPE_PREDICATES:
        return False

    if SIM_PAGE_SETTLE_SECONDS > 0:
        time.sleep(SIM_PAGE_SETTLE_SECONDS)

    if not _open_pref_network_dialog(device_id):
        return False

    if network_type == 5:
        # 无 5G 项时不滑动查找，避免弹框消失；当前屏无 5G 即视为不支持，改选 4G 自动
        if dialog_has_matching_row(
            device_id,
            pred_5g_auto_row,
            max_scrolls=PREF_NETWORK_DIALOG_MAX_SCROLLS,
        ):
            return _select_network_mode(
                device_id,
                pred_5g_auto_row,
                max_scrolls=PREF_NETWORK_DIALOG_MAX_SCROLLS,
            )
        return _select_network_mode(
            device_id,
            pred_lte234_auto_row,
            max_scrolls=PREF_NETWORK_DIALOG_MAX_SCROLLS,
        )

    return _select_network_mode(
        device_id,
        _NETWORK_TYPE_PREDICATES[network_type],
        max_scrolls=PREF_NETWORK_DIALOG_MAX_SCROLLS,
    )
