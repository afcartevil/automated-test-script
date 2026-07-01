from collections import Counter


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
