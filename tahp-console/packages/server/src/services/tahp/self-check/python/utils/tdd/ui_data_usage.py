"""SIM 详情页「移动数据用量」解析。"""

import re
import time

from utils.tdd.ui_automatic import click_by_match_keywords, dump_current_ui
from utils.tdd.ui_xml import collect_texts_from_xml

USAGE_TEXT_RE = re.compile(
    r"已使用[^0-9]*([\d.,]+)\s*(MB|GB)",
    re.IGNORECASE,
)
USAGE_TEXT_EN_RE = re.compile(
    r"used[^0-9]*([\d.,]+)\s*(MB|GB)",
    re.IGNORECASE,
)

DATA_USAGE_KEYWORDS = (
    "移动数据用量",
    "Mobile data usage",
    "Data usage",
)


def _usage_mb_from_match(value_str: str, unit: str) -> float:
    val = float(value_str.replace(",", "").replace("，", ""))
    if unit.upper() == "GB":
        return val * 1024.0
    return val


def parse_usage_texts(texts: list[str]) -> tuple[bool, float, str]:
    best_mb = 0.0
    best_snippet = ""
    joined = "\n".join(texts)
    for pattern in (USAGE_TEXT_RE, USAGE_TEXT_EN_RE):
        for match in pattern.finditer(joined):
            try:
                mb = _usage_mb_from_match(match.group(1), match.group(2))
            except ValueError:
                continue
            if mb > best_mb:
                best_mb = mb
                best_snippet = match.group(0)
    return best_mb > 0, best_mb, best_snippet


def read_mobile_data_usage_mb(device_id: str) -> tuple[bool, float, str]:
    """
    在当前 SIM 详情页点击「移动数据用量」并解析已使用流量。

    返回 (是否大于0, usage_mb, 匹配片段)。
    """
    if not device_id:
        return False, 0.0, ""
    if not click_by_match_keywords(
        device_id,
        DATA_USAGE_KEYWORDS,
        prefer_cached_ui=False,
        max_scrolls=8,
    ):
        return False, 0.0, ""
    time.sleep(1.2)
    xml_path = dump_current_ui(device_id)
    if xml_path is None:
        return False, 0.0, ""
    texts = collect_texts_from_xml(xml_path)
    return parse_usage_texts(texts)
