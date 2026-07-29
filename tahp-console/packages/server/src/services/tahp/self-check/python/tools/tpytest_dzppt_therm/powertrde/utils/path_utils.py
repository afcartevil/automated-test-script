import fnmatch
import glob
import os
import re
import sys

from pathlib import Path
from typing import Union, Optional, List, Tuple, Dict

PathLike = Union[str, Path]
VariantPath = Tuple[str, Path]


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


def find_largest_filename_include_text(directory, include_text, only='all'):
    """
    找到符合要求的最大的名称的文件绝对路径
    params:
    directory: 文件夹路径
    include_text: 包含的文本
    only: 'all' or 'file' or 'dir'
    """
    # 使用glob查找
    search_pattern = os.path.join(directory, f'*{include_text}*')
    files = glob.glob(search_pattern)

    # 检查是否找到文件
    if not files:
        return None

    if only == 'file':
        files = [f for f in files if os.path.isfile(f)]
    elif only == 'dir':
        files = [f for f in files if os.path.isdir(f)]

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


def get_top_level_folders(directory):
    """返回指定目录下的表层文件夹的绝对路径（不递归子目录）"""
    try:
        return [
            os.path.abspath(os.path.join(directory, name))
            for name in os.listdir(directory)
            if os.path.isdir(os.path.join(directory, name))
        ]
    except Exception:
        return []


def find_related_variants(
        pathlike: PathLike,
        *,
        include_self: bool = True,
        case_sensitive: Optional[bool] = None,
        tag_char_class: str = r'[^@\.\/\\]+'  # 默认 tag 不包含 '.', '/', '\' 或 '@'
) -> List[VariantPath]:
    """
    在给定路径的父目录表层查找所有与该路径“基名 + 可选 @tag ... + 相同后缀”形式相关的文件，
    并同时返回每个匹配文件对应的变体名称（位于基名与后缀之间的 '@...' 部分，不含最前导 '@'）。

    例如给定 target "config.pbtx"，会匹配:
      - config.pbtx                 -> variant ''
      - config@XIAOMI.pbtx          -> variant 'XIAOMI'
      - config@CN@v2.pbtx           -> variant 'CN@v2'

    参数:
      pathlike: 要关联的文件路径（Path 或 str），用于推断基名与后缀（文件可以不存在）。
      include_self: 是否把传入的同名文件包含在结果中（默认 True）。
      case_sensitive: 控制是否大小写敏感匹配。None 表示自动根据平台：Windows 不敏感，其他平台敏感。
      tag_char_class: 正则中 tag 的字符类（不含 @ 和 '.' 等），可自定义以放宽或收紧 tag 允许字符。

    返回:
      按文件名排序的 (Path, variant_name) 列表；variant_name 为空字符串表示“原始基文件”。
    """
    p = Path(pathlike)

    parent = p.parent
    if not parent.exists() or not parent.is_dir():
        raise FileNotFoundError(f"Parent directory does not exist or is not a directory: {parent!s}")

    # 默认平台大小写规则：Windows 不敏感，其它平台敏感
    if case_sensitive is None:
        case_sensitive = not (os.name == "nt" or sys.platform.startswith("win"))

    # 合成完整后缀（例如 '.tar.gz'）
    suffixes = ''.join(p.suffixes)  # 可能为空字符串
    # 基名 = 文件名去掉完整后缀
    base_name = p.name[: len(p.name) - len(suffixes)] if suffixes else p.name

    # 构造正则并捕获 tags 部分（可能为空）
    # tags 捕获形式为: (?:@tag)* 例如 "@CN@v2" 或为空
    # 使用 re.escape 保护 base_name 与 suffixes 中的特殊字符
    pattern = r'^' + re.escape(base_name) + r'(?P<tags>(?:@' + tag_char_class + r')*)' + re.escape(suffixes) + r'$'
    flags = 0 if case_sensitive else re.IGNORECASE
    prog = re.compile(pattern, flags)

    results: List[VariantPath] = []

    for entry in parent.iterdir():
        # 只关心文件（排除目录、链接指向目录等）
        try:
            if not entry.is_file():
                continue
        except Exception:
            # 无法访问该条目（权限等），跳过
            continue

        m = prog.match(entry.name)
        if not m:
            continue

        tags_raw = m.group('tags') or ''  # 例如 '@CN@v2' 或 ''
        # 我们返回的 variant_name 去掉最前导 '@'，若有多个 tag 则保持内部 '@' 连接，如 'CN@v2'
        if tags_raw:
            # tags_raw 以 '@' 开始，split 后第一个元素会是 ''，过滤掉空再 join
            tags_parts = [t for t in tags_raw.split('@') if t]  # ['CN', 'v2']
            variant_name = "@".join(tags_parts)  # 'CN@v2'
        else:
            variant_name = ""

        results.append((variant_name, entry))

    # 排序逻辑：按文件名排序，若 include_self=True 则尽量把与输入同名的文件放到首位
    def _a1(item):
        return item[1].name.lower()

    def _b1(a, b):
        return a.lower() == b.lower()

    def _a2(item):
        return item[0].name

    def _b2(a, b):
        return a == b

    if not case_sensitive:
        sort_key = _a1
        name_equal = _b1
    else:
        sort_key = _a2
        name_equal = _b2

    results.sort(key=sort_key)

    if include_self:
        # 把与输入名称相同（按大小写规则）的项移动到最前（若存在）
        for i, (_, pth) in enumerate(results):
            if name_equal(p.name, pth.name):
                if i != 0:
                    results.insert(0, results.pop(i))
                break
    else:
        # 过滤掉与输入同名的项
        results = [(pth, vn) for (pth, vn) in results if not name_equal(p.name, pth.name)]

    return results


def get_closest_variant_path_by_keys(target_variant_paths: List[VariantPath], keys: List[str],
                                     key_from_back_to_front: bool = True):
    default_variant = None
    if not keys:
        for f in target_variant_paths:
            if not f[0]:
                return f
    else:
        for k in (keys if not key_from_back_to_front else reversed(keys)):
            for f in (target_variant_paths if not key_from_back_to_front else reversed(target_variant_paths)):
                if not f[0]:
                    default_variant = f
                if f[0].lower() == k.lower():
                    return f
    return default_variant


def search_paths(
    root: str,
    pattern: str = "*",
    recursive: bool = True,
    include_dirs: bool = True,
    include_files: bool = True
) -> List[Dict[str, str]]:
    """
    通用文件/文件夹搜索函数

    Args:
        root: 搜索起始目录
        pattern: 文件名匹配模式（支持通配符，如 '*.py'、'test_*'）
        recursive: 是否递归搜索
        include_dirs: 是否包含文件夹
        include_files: 是否包含文件

    Returns:
        List[Dict[str, str]]: 每项为:
            {
                "path": 绝对路径,
                "relpath": 相对 root 的路径,
                "type": "file" 或 "dir"
            }
    """
    result = []
    root = os.path.abspath(root)

    if recursive:
        for dirpath, dirnames, filenames in os.walk(root):
            if include_dirs:
                for d in dirnames:
                    if fnmatch.fnmatch(d, pattern):
                        abs_path = os.path.join(dirpath, d)
                        result.append({
                            "path": abs_path,
                            "relpath": os.path.relpath(abs_path, root),
                            "type": "dir",
                        })
            if include_files:
                for f in filenames:
                    if fnmatch.fnmatch(f, pattern):
                        abs_path = os.path.join(dirpath, f)
                        result.append({
                            "path": abs_path,
                            "relpath": os.path.relpath(abs_path, root),
                            "type": "file",
                        })
    else:
        for entry in os.scandir(root):
            if entry.is_dir() and include_dirs and fnmatch.fnmatch(entry.name, pattern):
                result.append({
                    "path": os.path.abspath(entry.path),
                    "relpath": os.path.relpath(entry.path, root),
                    "type": "dir",
                })
            elif entry.is_file() and include_files and fnmatch.fnmatch(entry.name, pattern):
                result.append({
                    "path": os.path.abspath(entry.path),
                    "relpath": os.path.relpath(entry.path, root),
                    "type": "file",
                })

    return result


if __name__ == '__main__':
    print(find_related_variants(Path(r'D:\Projects\dz_auto_env\config\dzppt\pcss\config_continuous_start\config1.pbtx')))
