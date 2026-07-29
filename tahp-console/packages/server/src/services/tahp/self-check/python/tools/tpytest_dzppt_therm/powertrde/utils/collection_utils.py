from collections import Counter
from collections.abc import Mapping as MappingABC
from typing import Any, Mapping


def resize_list(lst, target_size):
    """
    Resize a list to the target size by either truncating it or appending None values.

    Args:
        lst (list): The list to be resized.
        target_size (int): The target size of the list.

    Returns:
        list: The resized list.
    """
    current_size = len(lst)

    if current_size > target_size:
        # Truncate the list
        return lst[:target_size]
    elif current_size < target_size:
        # Extend the list with None
        return lst + [None] * (target_size - current_size)
    else:
        # The list is already the target size
        return lst


def filter_dict_by_keys(original_dict: dict, keys_list: list):
    """
    过滤字典中key等于列表的值的键值对，并将新的键值对组成新的字典返回

    :param original_dict: 原始字典
    :param keys_list: 要保留的键的列表
    :return: 过滤后的新字典
    """
    new_dict = {}
    for key in keys_list:
        if key in original_dict:
            new_dict[key] = original_dict[key]
    return new_dict


def are_lists_equal(list1, list2, with_count: bool = True):
    """
    比较两个列表是否相等，可以选择忽略元素出现的次数
    """
    # 如果两个列表都为 None，返回 True
    if list1 is None and list2 is None:
        return True
    # 如果其中一个列表为 None，另一个不为 None，返回 False
    if list1 is None or list2 is None:
        return False
    if with_count:
        return Counter(list1) == Counter(list2)
    else:
        return set(list1) == set(list2)


def index_or_default(lst: list, value, default=-1) -> int:
    """
    返回 value 在 lst 中的索引位置；若未找到，则返回 default。
    """
    try:
        return lst.index(value)
    except ValueError:
        return default


def _strip_obj(obj: Any, rem_depth: int) -> Any:
    """
    内部递归：
      rem_depth 表示“还可以向下递归的层数”（不包含当前层）。
      当 rem_depth == 0 时：不再进入子容器，只对遇到的 str 做 strip；
      当 rem_depth > 0 时：可以进入子容器，并在递归调用时把 rem_depth-1 传下去。
    """
    # 字符串：总是 strip
    if isinstance(obj, str):
        return obj.strip()

    # 映射 / dict-like
    if isinstance(obj, MappingABC):
        result = {}
        for k, v in obj.items():
            new_k = k.strip() if isinstance(k, str) else k
            if isinstance(v, str):
                new_v = v.strip()
            elif rem_depth > 0:
                # 允许进入子容器：递归处理，深度减 1
                new_v = _strip_obj(v, rem_depth - 1)
            else:
                # rem_depth == 0：不进入子容器，保持原值（但字符串已在前面处理）
                new_v = v
            result[new_k] = new_v
        return result

    # list/tuple/set 等序列容器
    if isinstance(obj, list):
        if rem_depth > 0:
            return [_strip_obj(x, rem_depth - 1) for x in obj]
        else:
            # rem_depth == 0: 不进入子容器，保持原样
            return obj

    if isinstance(obj, tuple):
        if rem_depth > 0:
            return tuple(_strip_obj(x, rem_depth - 1) for x in obj)
        else:
            return obj

    if isinstance(obj, set):
        if rem_depth > 0:
            # 处理后可能产生不可哈希元素（若子元素变成 dict），这将抛异常；
            # 若希望更稳健可改为返回 list，但这里保留 set 行为。
            return {_strip_obj(x, rem_depth - 1) for x in obj}
        else:
            return obj

    # 其他类型不处理
    return obj


def strip_dict(d: Mapping[str, Any], *, max_depth: int = 0) -> dict:
    """
    将字典 d 的键和值进行 strip，并按 max_depth 递归处理嵌套结构。
    语义说明：
      - max_depth 表示从顶层开始可以向下递归的层数（不包含顶层）。
        * max_depth=0: 仅处理顶层（strip keys 和顶层为 str 的 values），不进入任何嵌套容器。
        * max_depth=1: 处理顶层并进入直接子容器一层（对子容器内的字符串进行 strip）。
        * 以此类推。
    参数:
      d: 一个 Mapping（通常为 dict）
      max_depth: int，向下递归深度（非负整数），默认 2
    返回:
      新的 dict（不修改原始 d）
    注意:
      - 仅对 str 类型 key 做 strip；非 str key 保持不变。
      - strip 可能导致 key 冲突（例如 " a " 和 "a"），后出现的会覆盖前面的项。
    """
    if not isinstance(d, MappingABC):
        raise TypeError("strip_dict expects a mapping (dict-like) as first argument")
    if not isinstance(max_depth, int) or max_depth < 0:
        raise ValueError("max_depth must be a non-negative integer")

    # rem_depth 初始等于 max_depth（表示还可以往下进入的层数）
    return _strip_obj(d, max_depth)
