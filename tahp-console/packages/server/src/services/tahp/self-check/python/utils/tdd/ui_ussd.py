"""USSD 错误弹框检测与关闭。"""

import time

from utils.tdd.ui_automatic import click_by_match_keywords, dump_current_ui
from utils.tdd.ui_xml import collect_texts_from_xml

DISMISS_KEYWORDS = ("确定", "确认", "OK", "关闭", "取消", "知道了", "Dismiss")
ERROR_HINTS = ("失败", "错误", "无效", "不支持", "无法", "failed", "error", "invalid")
DEFAULT_DIALOG_WAIT_SECONDS = 30.0
DEFAULT_DIALOG_POLL_INTERVAL = 1.0


def ussd_error_dialog_visible(device_id: str) -> bool:
    xml_path = dump_current_ui(device_id)
    if xml_path is None:
        return False
    texts = collect_texts_from_xml(xml_path)
    joined = "\n".join(texts).lower()
    return any(h.lower() in joined for h in ERROR_HINTS)


def wait_ussd_error_dialog(
    device_id: str,
    *,
    timeout_seconds: float = DEFAULT_DIALOG_WAIT_SECONDS,
    poll_interval: float = DEFAULT_DIALOG_POLL_INTERVAL,
) -> bool:
    """轮询等待 USSD 错误弹框出现。"""
    deadline = time.monotonic() + max(0.0, timeout_seconds)
    while time.monotonic() < deadline:
        if ussd_error_dialog_visible(device_id):
            return True
        time.sleep(max(0.1, poll_interval))
    return False


def dismiss_ussd_error_dialog(device_id: str) -> bool:
    if not ussd_error_dialog_visible(device_id):
        return True
    if click_by_match_keywords(device_id, DISMISS_KEYWORDS, max_scrolls=2):
        time.sleep(0.5)
        return not ussd_error_dialog_visible(device_id)
    return False
