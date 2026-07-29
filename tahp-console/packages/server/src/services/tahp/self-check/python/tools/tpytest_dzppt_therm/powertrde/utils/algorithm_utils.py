import hashlib
import math
import re
from typing import Callable, Any, TypeVar, Iterable, List, Optional
from typing import Tuple

T = TypeVar('T')


def deep_search(search_node, search_path: list, predicate: Callable[[Any, Any], bool]):
    def dfs(tree, path, depth):
        path_key = path[depth]
        for node in tree:
            if predicate(node, path_key):
                if depth == len(path) - 1:
                    return node
                return dfs(node, path, depth + 1)
        return None

    return dfs(search_node, search_path, 0)


def match_char_symbol_pair(input_str: str, symbol_left: str, symbol_right: str, start_index: int = 0,
                           end_index: int = -1) \
        -> Tuple[int, int]:
    symbol_count = 0
    symbol_left_index = -1
    len_str = len(input_str)
    for i in range(start_index, len_str if end_index < 0 else min(end_index, len_str)):
        if input_str[i] == symbol_left:
            if symbol_count == 0:
                symbol_left_index = i
            symbol_count += 1
        elif input_str[i] == symbol_right:
            symbol_count -= 1
            if symbol_count == 0:
                return symbol_left_index, i
    return -1, -1


def simple_line_match(input_string: str, pattern: str) -> bool:
    """
    简单的单行文字匹配器，支持普通字符和'*'字符的自定义规则。

    :param input_string: 输入的字符串
    :param pattern: 自定义的匹配规则
    :return: 匹配成功返回True，失败返回False
    """
    # 将自定义规则中的'*'替换为正则表达式的'.*'
    regex_pattern = '^' + re.escape(pattern).replace(r'\*', '.*') + '$'

    # 使用正则表达式进行匹配
    match = re.match(regex_pattern, input_string)
    return match is not None


def nearest_power_of_2(value: float) -> int:
    if value <= 0:
        raise ValueError("The value must be a positive number.")
    upper_power = 2 ** math.ceil(math.log2(value))
    lower_power = 2 ** math.floor(math.log2(value))
    if (upper_power - value) < (value - lower_power):
        return upper_power
    else:
        return lower_power


def calculate_md5(input_string: str) -> str:
    md5_hash = hashlib.md5()
    md5_hash.update(input_string.encode('utf-8'))
    return md5_hash.hexdigest()


def calculate_file_md5(file_path):
    # 使用 hashlib 模块计算文件的 MD5 值
    md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        # 以文件块的方式更新 MD5 值，适用于大文件
        for chunk in iter(lambda: f.read(4096), b""):
            md5.update(chunk)
    # 返回 MD5 值的十六进制表示
    return md5.hexdigest()


def compare_versions(version1: str, version2: str) -> int:
    parts1 = version1.split('.')
    parts2 = version2.split('.')

    max_length = max(len(parts1), len(parts2))

    for i in range(max_length):
        part1 = int(parts1[i]) if i < len(parts1) else 0
        part2 = int(parts2[i]) if i < len(parts2) else 0

        if part1 > part2:
            return 1
        elif part1 < part2:
            return -1

    return 0


def format_to_two_decimals(num):
    # 使用 round 保留最多两位小数
    rounded_num = round(num, 2)
    if rounded_num == int(rounded_num):
        return int(rounded_num)  # 返回整数部分
    else:
        return rounded_num  # 返回浮点数，最多两位小数(num):


def split_into_chunks(data: Iterable[T]) -> List[List[T]]:
    """
    将 data 分为若干组。

    如果指定了 n：
    - 将 data 平分为 n 份，返回一个长度为 n 的列表

    如果未指定 n（自动分组）：
    - < 10 个数据：分为 1 组
    - 10~20 个数据：分为 2 组
    - > 20 个数据：分为 3 组

    :param data: 任意可迭代对象
    :param n: 可选，要分成的块数。如果为 None 则自动确定分组数量
    :return: 分组后的列表
    """
    lst = list(data)
    length = len(lst)

    # 自动确定分组数量
    if length < 10:
        n = 1
    elif length <= 20:
        n = 2
    elif length <= 30:
        n = 3
    else:
        n = 5

    # 基本块大小和需要多分配 1 个元素的块数量
    base_size, remainder = divmod(length, n)

    chunks: List[List[T]] = []
    start = 0
    for i in range(n):
        # 当前块大小 = base_size + (i < remainder ? 1 : 0)
        size = base_size + (1 if i < remainder else 0)
        chunks.append(lst[start:start + size])
        start += size

    return chunks


def distribute_ranges(num_tasks: int, num_units: int) -> List[Optional[Tuple[float, float]]]:
    """
    将 num_tasks 个任务按最均匀的比例分配给 num_units 个工作单元，
    并返回每个单元负责的“任务区间”列表。

    参数:
      num_tasks (int): 待分配的总任务数，必须 ≥ 0。
      num_units (int): 负责执行任务的单元数量，必须 ≥ 1。

    返回:
      List[Optional[Tuple[float, float]]]: 长度为 num_units 的列表，
        其中第 i 个元素为 (start_ratio, end_ratio) 或 None：
          - start_ratio = 该单元第一个任务索引 / num_tasks
          - end_ratio   = 该单元最后一个任务索引 +1 / num_tasks
        如果 num_tasks==0 或该单元没有任务，则对应位置为 None。

    算法说明:
      1. 计算 base = num_tasks // num_units，每个单元至少分到 base 个任务。
      2. 计算 r = num_tasks % num_units，将剩余 r 任务依次分给前 r 个单元，每人多 1。
      3. 用滚动的 start_idx 依次累加分配数量，计算各自的 [start, end) 区间并归一化。

    用例示例:
      >>> distribute_ranges(5, 3)
      [(0.0, 0.3333333333333333),
       (0.3333333333333333, 0.6666666666666666),
       (0.6666666666666666, 1.0)]

      >>> distribute_ranges(3, 4)
      [(0.0, 0.3333333333333333),
       (0.3333333333333333, 0.6666666666666666),
       (0.6666666666666666, 1.0),
       None]
    """
    if num_units < 1:
        raise ValueError(f"num_units must be >=1, got {num_units}")
    # 没有任务，所有单元返回 None
    if num_tasks <= 0:
        return [None] * num_units

    base = num_tasks // num_units
    r = num_tasks % num_units

    intervals: List[Optional[Tuple[float, float]]] = []
    start_idx = 0

    for i in range(num_units):
        # 每个单元分到的任务数量
        count = base + (1 if i < r else 0)
        if count == 0:
            intervals.append(None)
        else:
            end_idx = start_idx + count
            intervals.append((start_idx / num_tasks, end_idx / num_tasks))
            start_idx = end_idx

    return intervals


def get_unit_work_interval(total_workload: int, num_units: int, unit_index: int) -> Optional[Tuple[float, float]]:
    """
    获取“第 unit_index 个工作单元”在 total_workload 总工作量上的归一化处理区间 [start, end)。

    参数:
      total_workload (int): 总工作量（例如用例数、数据条数等），必须 >= 0。
      num_units      (int): 工作单元总数（例如设备数、进程数等），必须 >= 1。
      unit_index     (int): 本单元的索引（0 起），0 <= unit_index < num_units。

    返回:
      - 若该单元分配到至少 1 个工作，则返回 (start_ratio, end_ratio)，
        表示它负责的工作量索引范围占总体的比例；
      - 若未分配到任何工作，则返回 None。

    算法简述:
      1. 均分基数 base = total_workload // num_units
      2. 余数 extra   = total_workload % num_units
      3. 本单元实际分配 count = base + (1 if unit_index < extra else 0)
      4. 起始索引 start_idx = base * unit_index + min(unit_index, extra)
      5. 结束索引 end_idx   = start_idx + count
      6. 比例区间 = (start_idx/total_workload, end_idx/total_workload)

    示例:
      >>> get_unit_work_interval(10, 4, 0)
      (0.0, 0.25)      # 0–2 号任务，25%
      >>> get_unit_work_interval(10, 4, 1)
      (0.25, 0.5)      # 2–4 号任务
      >>> get_unit_work_interval(3, 4, 3)
      None             # 第 3 台设备无任务
    """
    if num_units < 1:
        raise ValueError(f"num_units 必须 >= 1，收到 {num_units}")
    if not (0 <= unit_index < num_units):
        raise ValueError(f"unit_index 应在 [0, {num_units}) 之间，收到 {unit_index}")
    if total_workload <= 0:
        return None

    base = total_workload // num_units
    extra = total_workload % num_units

    count = base + (1 if unit_index < extra else 0)
    if count == 0:
        return None

    start_idx = base * unit_index + min(unit_index, extra)
    end_idx = start_idx + count

    return start_idx / total_workload, end_idx / total_workload
