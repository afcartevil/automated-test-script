import glob
import os

from pathlib import Path


def find_largest_filename_with_prefix(directory, prefix):
    # 使用glob查找以prefix开头的所有文件
    search_pattern = os.path.join(directory, prefix + '*')
    files = glob.glob(search_pattern)

    # 检查是否找到文件
    if not files:
        return None

    # 找到文件名字符串最大的文件
    largest_file = max(files, key=os.path.basename)

    # 返回文件的绝对路径
    return os.path.join(directory, largest_file)


def find_largest_filename_include_text(directory, include_text):
    # 使用glob查找
    search_pattern = os.path.join(directory, f'*{include_text}*')
    files = glob.glob(search_pattern)

    # 检查是否找到文件
    if not files:
        return None

    # 找到文件名字符串最大的文件
    largest_file = max(files, key=os.path.basename)

    # 返回文件的绝对路径
    return os.path.join(directory, largest_file)


def find_latest_folder(parent_directory):
    # 获取directory下的所有文件夹
    folders = [f for f in os.listdir(parent_directory) if os.path.isdir(os.path.join(parent_directory, f))]

    # 如果文件夹列表为空，返回None
    if not folders:
        return None

    # 找出最近修改的文件夹
    latest_folder = max(folders, key=lambda f: os.path.getmtime(os.path.join(parent_directory, f)))

    return latest_folder


def find_latest_file(parent_directory):
    # 获取directory下的所有文件（排除文件夹）
    files = [f for f in os.listdir(parent_directory) if os.path.isfile(os.path.join(parent_directory, f))]

    # 如果文件列表为空，返回None
    if not files:
        return None

    # 找出最近修改的文件
    latest_file = max(files, key=lambda f: os.path.getmtime(os.path.join(parent_directory, f)))

    return latest_file


def find_files_with_prefix(directory, prefix, include_dirs=False):
    """
    在指定目录中查找以指定前缀开头的文件（或文件夹，需将include_dirs置为True）。

    参数:
    directory (str): 文件夹路径。
    prefix (str): 文件名前缀。

    返回:
    list: 以指定前缀开头的文件名列表。
    """
    # 检查目录是否存在
    if not os.path.isdir(directory):
        raise ValueError(f"目录 '{directory}' 不存在")

    # 初始化结果列表
    matching_files = []

    # 遍历目录中的所有项目
    for item in os.listdir(directory):
        item_path = os.path.join(directory, item)
        # 检查项目是否是文件（或包含文件夹）且以指定前缀开头
        if (include_dirs or os.path.isfile(item_path)) and item.startswith(prefix):
            matching_files.append(item_path)

    return matching_files


def get_unique_path(original_path: str) -> str:
    """
    生成一个不重名的绝对路径，如果 original_path 已存在，则在 basename 前加 `_1`、`_2` 递增后缀，直到找到一个可用路径。

    :param original_path: 原始绝对路径
    :return: 一个确保不重名的新路径
    """
    path = Path(original_path).resolve()  # 规范化路径
    if not path.exists():
        return str(path)  # 如果路径不存在，直接返回

    parent = path.parent  # 获取父目录
    stem = path.stem  # 获取文件名（无后缀）
    suffix = path.suffix  # 获取文件后缀
    counter = 1

    while True:
        new_path = parent / f"{stem}_{counter}{suffix}"
        if not new_path.exists():
            return str(new_path)
        counter += 1
