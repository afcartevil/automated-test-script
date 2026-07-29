import re
from typing import List, Optional

COMMA_OR_CHINESE = [',', '，']
COLON_OR_CHINESE = [':', '：']
SEMICOLON_OR_CHINESE = [';', '；']


def surround_with_html_font_color(text: str, color: str) -> str:
    return f'<font color="{color}">{text}</font>'


def split_text_by_symbols(input_text: str, symbols: List[str], strip: bool = False, remove_empty_entry: bool = False):
    # 将符号列表转换为正则表达式模式
    pattern = '|'.join(map(re.escape, symbols))

    # 使用正则表达式进行分割
    split_list = re.split(pattern, input_text)

    # 如果需要 strip 操作
    if strip:
        split_list = [item.strip() for item in split_list]

    # 如果需要移除空的分割结果
    if remove_empty_entry:
        split_list = [item for item in split_list if item]

    return split_list


def split_text(input_text: str, symbol: str, strip: bool = False, remove_empty_entry: bool = False):
    split_list = input_text.split(symbol)

    # 如果需要 strip 操作
    if strip:
        split_list = [item.strip() for item in split_list]

    # 如果需要移除空的分割结果
    if remove_empty_entry:
        split_list = [item for item in split_list if item]

    return split_list


def find_symbol(input_text: str, symbols: List[str], start_index: int = 0, end_index: Optional[int] = None):
    """
    在指定范围内查找字符串列表中的任一符号的第一个出现位置。

    参数:
    input_text (str): 输入的字符串。
    symbols (list): 需要查找的符号列表。
    start_index (int, 可选): 查找的起始索引，默认为0。
    end_index (int, 可选): 查找的结束索引（不包含该索引位置），默认为None，表示查找到字符串末尾。

    返回:
    tuple: 如果找到，返回 (位置, 找到的符号)；如果未找到，返回 (-1, None)。
    """
    if end_index is None or end_index == 0:
        end_index = len(input_text)

    # 确保start_index和end_index在合理范围内
    if start_index < 0:
        start_index = 0
    if end_index > len(input_text):
        end_index = len(input_text)

    # 初始值，表示未找到
    first_position = -1
    found_symbol = None

    # 遍历所有符号，查找其在指定范围内的第一次出现的位置
    for symbol in symbols:
        pos = input_text.find(symbol, start_index, end_index)
        if pos != -1 and (first_position == -1 or pos < first_position):
            first_position = pos
            found_symbol = symbol

    return first_position, found_symbol


def find_last_non_empty_line_start(input_text: str):
    """
    返回一个字符串中最后一个strip之后不为空的行的起始位置。
    如果没有找到这样的行，则返回-1。

    参数:
    input_text (str): 输入的字符串。

    返回:
    int: 最后一个strip之后不为空的行的起始位置，如果没有找到则返回-1。
    """
    lines = input_text.splitlines()

    # 从后往前遍历行
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].strip():
            # 返回符合条件的行的起始位置
            return input_text.rfind(lines[i])

    return -1


def get_substring_between_symbols(input_str: str, symbol_left: str, symbol_right: str, start_index: int = 0,
                                  end_index: int = -1) -> Optional[str]:
    left_index = input_str.find(symbol_left, start_index, end_index)
    if left_index < 0:
        return None
    left_index += len(symbol_left)
    right_index = input_str.find(symbol_right, left_index, end_index)
    if right_index < 0:
        return None
    return input_str[left_index:right_index]
