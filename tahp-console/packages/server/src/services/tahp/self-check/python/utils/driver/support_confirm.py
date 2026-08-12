"""功能支持人工确认：统一「支持 / 不支持」按钮，禁止走仅「知道了」的 ack。"""

from __future__ import annotations

from typing import Callable


def missing_item_notice(feature_name: str) -> str:
    return f"未找到{feature_name}测试项，请判断是否支持{feature_name}"


def missing_prop_notice(feature_name: str) -> str:
    return f"未找到{feature_name}属性，请判断是否支持{feature_name}"


def is_item_not_found_message(message: str | None) -> bool:
    text = (message or "").strip()
    return "未找到" in text and "测试项" in text


def ask_feature_support(
    manual_confirm: Callable[..., str] | None,
    notice: str,
) -> str:
    """弹出「支持 / 不支持」，返回 pass / fail / pending。"""
    if not callable(manual_confirm):
        return "pending"
    return manual_confirm(
        notice,
        pass_label="支持",
        fail_label="不支持",
    ) or "pending"
