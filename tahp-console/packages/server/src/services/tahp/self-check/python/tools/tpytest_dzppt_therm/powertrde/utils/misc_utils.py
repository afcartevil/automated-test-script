import importlib
import locale
import logging
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import traceback
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Dict, Tuple, Callable, Any, List, Union
import psutil

from powertrde.framework.tran_logger import t_log


def dynamic_import(module_name: str, package: str = None, default=None):
    """Import a module.

    The 'package' argument is required when performing a relative import. It
    specifies the package to use as the anchor point from which to resolve the
    relative import to an absolute import.

    """
    try:
        module = importlib.import_module(module_name, package)
        return module
    except ImportError:
        return default


_color_names: Optional[Dict[str, int]] = None


def run_as_async(sync_func, *args):
    import asyncio
    future = asyncio.get_running_loop().run_in_executor(None, sync_func, *args)
    return future


def _decode_bytes_with_fallback(b: bytes, encoding: str) -> str:
    """
    Decode bytes to str with fallbacks:
      1) try given encoding (strict)
      2) try given encoding with 'surrogateescape' (preserve undecodable bytes)
      3) try filesystem/default encoding with surrogateescape
      4) fallback to latin-1 (lossless 1:1 mapping)
    This avoids Windows code-page mapping errors while preserving data.
    """
    if b is None:
        return ""
    # 1) strict
    try:
        return b.decode(encoding)
    except Exception:
        pass
    # 2) encoding + surrogateescape
    try:
        return b.decode(encoding, errors="surrogateescape")
    except Exception:
        pass
    # 3) filesystem encoding + surrogateescape
    try:
        import sys
        fs_enc = sys.getfilesystemencoding() or sys.getdefaultencoding()
        return b.decode(fs_enc, errors="surrogateescape")
    except Exception:
        pass
    # 4) latin-1 as final fallback (never fails)
    return b.decode("latin-1")


def run_command_get_text_output_exit_code(
    args,
    shell: bool = False,
    encoding: str = "utf-8",
    capture_error_output: bool = True,
    timeout: Optional[Union[int, float]] = None
) -> Tuple[str, str, int]:
    """
    Execute a command and capture its stdout, stderr, and exit code,
    with an optional timeout that truly kills the child (and its descendants)
    even when shell=True.

    On timeout, returns (stdout_so_far, stderr_so_far + timeout marker, -1).

    Notes on improvements:
      - always read bytes from subprocess and decode here with robust fallback to avoid
        Windows code page mapping errors (e.g. "No mapping for the Unicode character...")
      - on POSIX use start_new_session=True; on Windows use CREATE_NEW_PROCESS_GROUP
      - on timeout, attempt graceful group termination, then force-kill if needed
    """
    # Prepare pipes (we'll read bytes)
    stdout_pipe = subprocess.PIPE
    stderr_pipe = subprocess.PIPE if capture_error_output else None

    # Platform-specific process group/session creation
    creationflags = 0
    start_new_session = False
    if os.name == "nt":
        # Windows: create new process group so CTRL_BREAK_EVENT targets it
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        # POSIX: create a new session (setsid) so we can kill the process group
        start_new_session = True

    # Start process (use Popen to consistently collect bytes and manage groups)
    proc = subprocess.Popen(
        args,
        shell=shell,
        stdout=stdout_pipe,
        stderr=stderr_pipe,
        creationflags=creationflags,
        start_new_session=start_new_session
    )

    try:
        try:
            # Wait and collect output as bytes
            out_bytes, err_bytes = proc.communicate(timeout=timeout)
            # proc.communicate returns bytes when Popen was created without text=True
            # but some platforms might return str in rare configs; defensive:
            if isinstance(out_bytes, str):
                out_bytes = out_bytes.encode(encoding, errors="surrogateescape")
            if capture_error_output and isinstance(err_bytes, str):
                err_bytes = err_bytes.encode(encoding, errors="surrogateescape")
            # decode with fallback
            out_str = _decode_bytes_with_fallback(out_bytes or b"", encoding)
            err_str = _decode_bytes_with_fallback(err_bytes or b"", encoding) if capture_error_output else ""
            return out_str, err_str, proc.returncode
        except subprocess.TimeoutExpired:
            # Timeout: attempt to kill the whole group / tree
            try:
                if os.name == "nt":
                    # Try graceful group interrupt first
                    try:
                        # CTRL_BREAK_EVENT requires process group and a console; it may fail if no console attached.
                        proc.send_signal(signal.CTRL_BREAK_EVENT)
                    except Exception:
                        # fallback: terminate the process
                        try:
                            proc.terminate()
                        except Exception:
                            pass
                    # give it a bit
                    time.sleep(0.2)
                    # if still alive, kill
                    if proc.poll() is None:
                        try:
                            proc.kill()
                        except Exception:
                            pass
                else:
                    # POSIX: kill the process group
                    try:
                        os.killpg(proc.pid, signal.SIGTERM)
                    except Exception:
                        # fallback to terminating single proc
                        try:
                            proc.terminate()
                        except Exception:
                            pass
                    # allow graceful shutdown a moment
                    time.sleep(0.2)
                    if proc.poll() is None:
                        try:
                            os.killpg(proc.pid, signal.SIGKILL)
                        except Exception:
                            try:
                                proc.kill()
                            except Exception:
                                pass
            except Exception:
                # best-effort - ignore errors during kill attempts
                pass

            # After kill attempts, collect remaining output (no timeout now)
            try:
                out_bytes, err_bytes = proc.communicate(timeout=5)
            except Exception:
                # If communicate still fails, try to read what we can
                try:
                    out_bytes = b""
                    err_bytes = b""
                    # proc.stdout / stderr may be None or closed; skip if so
                    if proc.stdout:
                        try:
                            out_bytes = proc.stdout.read() or b""
                        except Exception:
                            pass
                    if capture_error_output and proc.stderr:
                        try:
                            err_bytes = proc.stderr.read() or b""
                        except Exception:
                            pass
                except Exception:
                    out_bytes = b""
                    err_bytes = b""

            if isinstance(out_bytes, str):
                out_bytes = out_bytes.encode(encoding, errors="surrogateescape")
            if capture_error_output and isinstance(err_bytes, str):
                err_bytes = err_bytes.encode(encoding, errors="surrogateescape")

            out_str = _decode_bytes_with_fallback(out_bytes or b"", encoding)
            err_str = _decode_bytes_with_fallback(err_bytes or b"", encoding) if capture_error_output else ""
            # append timeout marker
            timeout_msg = f"[TIMEOUT] Exceeded {timeout}s"
            if err_str:
                if not err_str.endswith("\n"):
                    err_str = err_str + "\n"
                err_str = err_str + timeout_msg
            else:
                err_str = timeout_msg
            return out_str, err_str, -1

    finally:
        # Ensure file descriptors are closed
        try:
            if proc.stdout:
                proc.stdout.close()
        except Exception:
            pass
        try:
            if proc.stderr:
                proc.stderr.close()
        except Exception:
            pass
        # Ensure child is reaped
        try:
            if proc.poll() is None:
                proc.wait(timeout=0.1)
        except Exception:
            # ignore: process likely already terminated or cannot be waited now
            pass


def run_command_get_text_output(args, shell=False, check=False, encoding="utf-8",
                                include_error_output: bool = False) -> str:
    """
    执行命令并获取输出文本
    :return: 命令的输出
    """
    process = subprocess.run(args, shell=shell, check=check, stdout=subprocess.PIPE,
                             stderr=(subprocess.PIPE if include_error_output else None),
                             encoding=encoding, text=True)
    out_text = ""
    stdout_output = process.stdout
    if stdout_output:
        out_text = stdout_output
    if include_error_output:
        stderr_output = process.stderr
        if stderr_output:
            stderr_output = 'Error Outputs:\n' + stderr_output
            if out_text:
                out_text += '\n\n' + stderr_output
            else:
                out_text = stderr_output
    return out_text


def run_command(args, shell=False, check=False, encoding="utf-8"):
    """
    执行命令并输出结果
    """
    return subprocess.run(args, shell=shell, check=check, encoding=encoding)


def run_command_background(args, shell=False, creation_flags=0):
    """
    执行命令并输出结果
    """
    return subprocess.Popen(args, shell=shell, creationflags=creation_flags)


def run_command_detached(args, shell=False):
    """
    执行命令并完全脱离父进程
    """
    if os.name == 'nt':
        p = subprocess.Popen(args, shell=shell, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, close_fds=True,
                             creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                             start_new_session=True)
    else:
        p = subprocess.Popen(args, shell=shell, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, close_fds=True,
                             start_new_session=True)
    return p


@contextmanager
def temp_working_directory(new_dir):
    """
    临时更改工作目录
    调用示例：
    with working_directory('some_directory'):
        # do something within some_directory
    """
    prev_dir = os.getcwd()
    os.chdir(new_dir)
    try:
        yield
    finally:
        os.chdir(prev_dir)


def get_all_color_names() -> Dict[str, int]:
    global _color_names
    if _color_names is None:
        _color_names = {
            "black": 0xFF000000,
            "white": 0xFFFFFFFF,
            "red": 0xFFFF0000,
            "green": 0xFF00FF00,
            "blue": 0xFF0000FF,
            "yellow": 0xFFFFFF00,
            "cyan": 0xFF00FFFF,
            "magenta": 0xFFFF00FF,
            "gray": 0xFF888888,
            "grey": 0xFF888888,
            "orange": 0xFFFFA500,
            "lightgray": 0xFFD3D3D3,
            "lightgrey": 0xFFD3D3D3,
            "darkgray": 0xFFA9A9A9,
            "darkgrey": 0xFFA9A9A9,
            "purple": 0xFF800080,
            "teal": 0xFF008080,
            "navy": 0xFF000080,
            "maroon": 0xFF800000,
            "olive": 0xFF808000,
            "lime": 0xFF00FF00,
            "aqua": 0xFF00FFFF,
            "fuchsia": 0xFFFF00FF,
            "silver": 0xFFC0C0C0,
            "gold": 0xFFFFD700,
        }
    return _color_names


def parse_color(color_str: str) -> int:
    """
    将颜色名称或RGB字符串转换为int类型的颜色值。
    参数:
    :param color_str: 颜色名称（例如："red", "yellow"）或RGB字符串（例如："#FFF0F0"）。
    返回:
    :returns int类型的颜色值。
    """
    color_names = get_all_color_names()
    if color_str.lower() in color_names:
        color_int = color_names[color_str.lower()]
    elif color_str.startswith("#"):
        color = color_str.lstrip("#")
        if len(color) == 6:
            color = "FF" + color  # 如果没有提供alpha值，则添加全不透明
        elif len(color) != 8:
            raise ValueError("无效的RGB字符串格式。预期格式为#RRGGBB或#AARRGGBB。")
        color_int = int(color, 16)
    else:
        raise ValueError("无效的颜色名称或RGB字符串格式。")
    if color_int > 0x7FFFFFFF:
        color_int = color_int - 0x100000000
    return color_int


def find_folder_upwards(start_dir: str, find_file_name: str) -> Optional[str]:
    """
    从指定的起始目录开始，向上查找具有指定名称的文件夹。
    :param start_dir: 开始查找的目录。
    :param find_file_name: 要查找的文件或文件夹的名称。
    :return: 如果找到文件夹，则返回该文件夹的路径；否则返回None。
    """
    if not os.path.isdir(start_dir):
        raise ValueError("Provided path is not a directory")

    # 检查当前目录
    if os.path.exists(os.path.join(start_dir, find_file_name)):
        return start_dir

    # 获取当前目录的父目录
    parent_dir = os.path.dirname(start_dir)

    # 如果当前目录已经是根目录，则返回None
    if parent_dir == start_dir:
        return None

    # 递归调用，继续在父目录中查找
    return find_folder_upwards(parent_dir, find_file_name)


def is_run_in_exe() -> bool:
    """
    检查当前脚本是否在exe文件中运行。
    :return: 如果当前脚本在exe文件中运行，则返回True；否则返回False。
    """
    return getattr(sys, 'frozen', False)


def get_standard_time_str(include_ms: bool = False, specified_time: Optional[datetime] = None):
    """
    将当前时间格式化为类似 2024-08-06 15:54:34 这样的时间字符串
    如果 include_ms 置为 True，将返回类似 2024-08-06 15:54:34.789 这样的格式
    """
    if specified_time:
        current_time = specified_time
    else:
        current_time = time.localtime()
    if include_ms:
        formatted_time = current_time.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    else:
        formatted_time = current_time.strftime("%Y-%m-%d %H:%M:%S")
    return formatted_time


def get_standard_now_time_str(include_ms: bool = False):
    return get_standard_time_str(include_ms)


def get_digit_time_str(include_ms: bool = False, specified_time: Optional[datetime] = None):
    """
    将当前时间格式化为类似 20240806155434 这样的时间字符串
    如果 include_ms 置为 True，将返回类似 2024080615543478 这样的格式
    """
    if specified_time:
        current_time = specified_time
    else:
        current_time = datetime.now()
    if include_ms:
        formatted_time = current_time.strftime("%Y%m%d%H%M%S%f")[:-3]
    else:
        formatted_time = current_time.strftime("%Y%m%d%H%M%S")
    return formatted_time


def get_exact_digit_time_str(specified_time: Optional[datetime] = None):
    """
    将当前时间格式化为类似 20240806155434789 这样的精确时间字符串
    或提供一个指定的时间对象，返回精确时间字符串
    """
    if specified_time:
        current_time = specified_time
    else:
        current_time = datetime.now()
    formatted_time = current_time.strftime("%Y%m%d%H%M%S%f")
    return formatted_time


def get_date_time_filename_str(specified_time: Optional[datetime] = None, need_ms: bool = False):
    """
    将当前时间格式化为类似 20240806_155434 这样的精确到秒或者毫秒的时间字符串
    或提供一个指定的时间对象，返回时间字符串
    """
    if specified_time:
        current_time = specified_time
    else:
        current_time = datetime.now()
    ms_format = '%f' if need_ms else ''
    formatted_time = current_time.strftime("%Y%m%d_%H%M%S" + ms_format)
    return formatted_time


def read_all_text(file_path, encoding='utf-8'):
    """
    读取指定文件的全部内容。

    :param file_path: 文件路径。
    :param encoding: 文件编码格式，默认'utf-8'。
    :return: 文件内容的字符串表示。
    """
    with open(file_path, 'r', encoding=encoding) as file:
        content = file.read()
    return content


def read_lines(file_path, encoding='utf-8'):
    """
    读取指定文件的全部内容。

    :param file_path: 文件路径。
    :param encoding: 文件编码格式，默认'utf-8'。
    :return: 文件内容的字符串表示。
    """
    with open(file_path, 'r', encoding=encoding) as file:
        content = file.readlines()
    return content


def write_all_text(file_path, content: str, encoding='utf-8'):
    """
    将指定的字符串写入到文件中。如果文件不存在则创建它，如果文件已经存在则覆盖它。

    :param file_path: 文件路径。
    :param content: 要写入文件的字符串。
    :param encoding: 文件编码，默认为'utf-8'。
    """
    with open(file_path, 'w', encoding=encoding) as file:
        file.write(content)


def get_local_time_string(unix_timestamp_ms: int) -> str:
    """
    将Unix时间戳（毫秒）转换为本地时间字符串。
    """
    # 将毫秒级时间戳转换为秒级时间戳
    timestamp_sec = unix_timestamp_ms / 1000

    # 转换为 datetime 对象
    dt = datetime.fromtimestamp(timestamp_sec)

    # 格式化为指定的字符串格式
    return dt.strftime('%Y-%m-%d %H:%M:%S')


def parse_timestamp(timestamp_str: str) -> datetime:
    """
    解析时间戳字符串为datetime对象。
    :param timestamp_str: 时间戳字符串，格式可以是 "YYYY-MM-DD HH:MM:SS" 或 "YYYY-MM-DD HH:MM:SS.SSS"。
    :return: datetime对象。
    """
    # 自动判断格式并解析字符串为datetime对象
    try:
        if '.' in timestamp_str:
            # 包含毫秒部分
            datetime_obj = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S.%f")
        else:
            # 不包含毫秒部分
            datetime_obj = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
        return datetime_obj
    except ValueError as e:
        raise ValueError(f"Incorrect date format: {e}")


def get_apk_file_version(apk_path):
    from apkutils2 import APK
    from powertrde.utils.apkutils2_extends import apkutils2_patcher
    apkutils2_patcher.patch()
    try:
        # 加载APK文件
        apk = APK(apk_path)
        # 获取版本号
        manifest = apk.get_manifest()
        v = manifest.get('@android:versionName') or manifest.get('versionName')
        return v
    except Exception as e:
        t_log.error(f"Error parsing APK file version number: {e}")
        return None


def get_apk_file_version_code(apk_path) -> Optional[int]:
    from apkutils2 import APK
    from powertrde.utils.apkutils2_extends import apkutils2_patcher
    apkutils2_patcher.patch()
    try:
        # 加载APK文件
        apk = APK(apk_path)
        # 获取版本号
        manifest = apk.get_manifest()
        v = manifest.get('@android:versionCode') or manifest.get('versionCode')
        return v
    except Exception as e:
        t_log.error(f"Error parsing APK file version code: {e}")
        return None


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


def switch_to_target_parent_dir(target_basename: str, max_levels: int) -> None:
    """
    检查当前工作路径的 basename 是否为 target_basename，
    如果不是，则向上查找，直到找到对应的全路径，
    并切换工作目录到这个路径。如果向上查找超过 max_levels 或者到达根目录仍未找到，
    则抛出异常。
    """
    current_dir = os.getcwd()
    levels_up = 0

    while True:
        # 获取当前目录的 basename
        current_basename = os.path.basename(current_dir)
        if current_basename == target_basename:
            # 找到目标目录，切换工作路径
            os.chdir(current_dir)
            return

        # 检查是否到达根目录
        parent_dir = os.path.dirname(current_dir)
        if current_dir == parent_dir:
            # 已到达顶层
            raise Exception(f"未在顶层目录中找到目标目录：{target_basename}")

        # 检查是否超过最大允许向上层数
        levels_up += 1
        if levels_up > max_levels:
            raise Exception(f"向上查找超过 {max_levels} 层，仍未找到目标目录：{target_basename}")

        # 更新当前目录为上级目录
        current_dir = parent_dir


def convert_dict_to_lowercase_key_dict(input_dict: dict, recursive=False):
    """
    将字典的键转换为小写。如果转换后出现重复键，则抛出ValueError。
    根据参数决定是否递归地转换嵌套字典的键。

    :param input_dict: 输入的字典
    :param recursive: 是否递归处理嵌套字典，默认为False
    :return: 转换后的字典，所有键均为小写
    :raises ValueError: 如果转换后出现重复键
    """
    lower_dict = {}
    for key, value in input_dict.items():
        # 仅处理字符串类型的键
        lower_key = key.lower() if isinstance(key, str) else key

        if lower_key in lower_dict:
            t_log.warning(f"Duplicate key found after conversion: '{lower_key}'")

        # 如果值是字典，根据recursive参数决定是否递归转换
        if recursive and isinstance(value, dict):
            lower_dict[lower_key] = convert_dict_to_lowercase_key_dict(value, recursive=True)
        else:
            lower_dict[lower_key] = value
    return lower_dict


def wait_for_result(sub_method, timeout: float, interval: float = 0.1):
    """
    在给定的时间内等待子方法返回非None的结果。

    :param sub_method: 一个不接受参数的子方法
    :param timeout: 等待的最大时间（以秒为单位）
    :param interval: 每次运行sub_method等待的时长
    :return: 子方法返回的非None结果，或者在超时后返回None
    """
    start_time = time.time()

    while True:
        result = sub_method()
        if result is not None:
            return result

        elapsed_time = time.time() - start_time
        remaining_time = timeout - elapsed_time

        # 如果剩余时间已经不足间隔时间，则直接等待剩余时间
        if remaining_time <= 0:
            break
        else:
            time.sleep(min(interval, remaining_time))

    return None


def get_timezone_delta():
    # 获取当前时区的偏移秒数
    offset_seconds = time.timezone if (time.localtime().tm_isdst == 0) else time.altzone
    # 将秒数转换为timedelta对象
    offset = timedelta(seconds=-offset_seconds)
    return offset


def format_seconds_to_time(seconds):
    """
    将浮点数格式的时间长度（秒）转换为 "HH:MM:SS" 格式的时间字符串

    :param seconds: float, 表示时间的秒数
    :return: str, 格式化的时间字符串
    """
    if seconds < 0:
        raise ValueError("时间长度不能为负数")

    # 使用内置 divmod 函数进行逐步拆解
    seconds = int(round(seconds))  # 将秒数四舍五入并转换为整数处理
    hours, remainder = divmod(seconds, 3600)  # 计算小时和余下的秒数
    minutes, seconds = divmod(remainder, 60)  # 计算分钟和余下的秒数

    # 格式化为 "HH:MM:SS"
    return f"{hours:02}:{minutes:02}:{seconds:02}"


def compare_versions(version1: str, version2: str) -> int:
    """
    比较两个版本号的大小。
    :param version1: 第一个版本号字符串，例如 "1.0.0"
    :param version2: 第二个版本号字符串，例如 "1.0.1"
    :return: 如果版本号相同返回 0；如果 version1 < version2 返回 -1；如果 version1 > version2 返回 1
    """
    from packaging.version import Version
    v1 = Version(version1)
    v2 = Version(version2)

    if v1 < v2:
        return -1
    elif v1 > v2:
        return 1
    else:
        return 0


def retry_func(func: Callable, attempts: int, exceptions=(Exception,),
               on_exception: Optional[Callable[[BaseException, int], Any]] = None,
               func_args: Optional[tuple] = None,
               func_kwargs: Optional[dict] = None):
    """
    尝试执行一个函数，如果函数执行失败，则重试。
    :param func: 要执行的函数
    :param attempts: 重试次数
    :param exceptions: 允许重试的异常类型
    :param on_exception: 在每次重试失败时调用的函数，接收两个参数：异常类型和重试次数，返回一个布尔值，
                         如果返回True，则继续重试；如果返回False，则抛出异常。默认为None，表示不处理异常。
    :param func_args: 函数的参数元组，默认为None，表示没有参数。
    :param func_kwargs: 函数的参数字典，默认为None，表示没有参数。
    """
    if func_args is None:
        func_args = ()
    if func_kwargs is None:
        func_kwargs = {}

    for i in range(attempts):
        try:
            func(*func_args, **func_kwargs)
            break
        except exceptions as e:
            if on_exception:
                r = on_exception(e, i)
                if r is not None and not r:
                    raise
            if i == attempts - 1:
                raise


def search_all_running_process(process_name: str, use_regex: bool = False) -> List[psutil.Process]:
    """
    搜索特定名称的进程是否正在运行，支持正则表达式匹配。

    :param process_name: 要检查的进程名称 (str)
    :param use_regex: 是否使用正则表达式匹配进程名称 (bool)，默认 False
    :return: 如果进程正在运行，返回 进程实例；否则返回 None
    """
    processes = []
    for process in psutil.process_iter(['name']):
        try:
            current_process_name = process.info['name']
            if use_regex:
                # 使用正则表达式匹配
                if re.search(process_name, current_process_name):
                    processes.append(process)
            else:
                # 使用精确匹配
                if current_process_name == process_name:
                    processes.append(process)
        except psutil.NoSuchProcess:
            # 忽略进程不存在的异常
            pass
    return processes


def search_running_process(process_name: str, use_regex: bool = False) -> Optional[psutil.Process]:
    """
    检查特定名称的正在运行中的进程，支持正则表达式匹配。

    :param process_name: 要检查的进程名称 (str)
    :param use_regex: 是否使用正则表达式匹配进程名称 (bool)，默认 False
    :return: 如果进程正在运行，返回 进程实例；否则返回 None
    """
    for process in psutil.process_iter(['name']):
        try:
            current_process_name = process.info['name']
            if use_regex:
                # 使用正则表达式匹配
                if re.search(process_name, current_process_name):
                    return process
            else:
                # 使用精确匹配
                if current_process_name == process_name:
                    return process
        except psutil.NoSuchProcess:
            # 忽略进程不存在的异常
            pass
    return None


def is_process_running(process_name: str, use_regex: bool = False) -> bool:
    return bool(search_running_process(process_name, use_regex))


def parse_args_to_dict(argv: List[str], drop_empty_keys: bool = True) -> Dict[str, str]:
    """
    解析 CLI 参数为字典，支持以下形式并自动去除值两端引号：
    - "--key=value"
    - "--key value"
    - "-key value"

    额外行为：当遇到没有显式值的键（例如 "--a --b 1" 中的 "--a"），通过
    参数 "drop_empty_keys" 控制：
    - True（默认）：丢弃该键，不写入结果字典；
    - False：保留该键，值设为空字符串 ""。

    Args:
        argv (list[str]): 一般传 sys.argv[1:]
        drop_empty_keys (bool): 是否剔除空值键，默认 True。

    Returns:
        dict[str, str]: 解析后的字典
    """
    result = {}
    n = len(argv)
    i = 0
    while i < n:
        arg = argv[i]
        if arg.startswith('--') or arg.startswith('-'):
            if '=' in arg:
                k, v = arg.lstrip('-').split('=', 1)
                v = v.strip()
                if (len(v) >= 2 and v[0] == '"' and v[-1] == '"') or (len(v) >= 2 and v[0] == "'" and v[-1] == "'"):
                    v = v[1:-1]
                result[k] = v
                i += 1
                continue
            k = arg.lstrip('-')
            if i + 1 < n:
                v = argv[i + 1].strip()
                if not v.startswith('-') or (v.startswith('-') and (v.startswith("-\"") or v.startswith("-'"))):
                    if (len(v) >= 2 and v[0] == '"' and v[-1] == '"') or (len(v) >= 2 and v[0] == "'" and v[-1] == "'"):
                        v = v[1:-1]
                    result[k] = v
                    i += 2
                    continue
            if not drop_empty_keys:
                result[k] = ""
            i += 1
            continue
        i += 1
    return result


def get_host_local_region():
    """
    获取主机的地区配置。

    Returns:
        str: 主机地区配置（例如语言和地区），或者在失败时返回错误信息。
    """
    # 获取系统的默认语言和地区设置
    lang_region, encoding = locale.getdefaultlocale()

    if lang_region:
        return lang_region
    else:
        return ""


def is_host_local_china():
    return get_host_local_region().startswith('zh_')


def copy_logger_log_file(logger, destination_path, target_file_handler_type=logging.FileHandler):
    """
    安全拷贝正在写入的日志文件。

    Args:
        logger (logging.Logger): 目标logger对象。
        destination_path (str): 日志文件拷贝的目标路径。
        target_file_handler_type: 目标 FileHandler
    """
    for handler in logger.handlers:
        if isinstance(handler, target_file_handler_type):
            # 确保文件Handler的缓冲区已刷新到文件
            handler.flush()
            # 获取日志文件路径
            log_file_path = handler.baseFilename

            # 拷贝日志文件
            shutil.copy(log_file_path, destination_path)
            return


def sanitize_filename(name: str) -> str:
    """
    将任意字符串转换为跨平台安全的“纯基名”，保留所有 Unicode 字母和数字，
    只替换以下字符：
      - 空格    → '_'
      - '/' '\\'→ '-'
      - '(' ')'→ '（' '）'
      - Windows 禁用字符 <>:"*?| 及其它非字母数字下划线短横和中文圆括号 → '_'
    去掉扩展名后：
      - 合并多重 '_' 或 '-' 为单个
      - 去掉首尾的 '_' 或 '-'
      - 若结果为空，返回 '_'
    """
    # 1. 去掉扩展名
    # base = os.path.splitext(name)[0]
    base = name

    # 2. 定义替换映射
    mapping = {
        ' ': '_',
        '/': '-',
        '\\': '-',
        '(': '（',
        ')': '）',
        '<': '_', '>': '_',
        ':': '_', '*': '_',
        '?': '_', '"': '_',
        '|': '_'
    }

    result = []
    for ch in base:
        if ch in mapping:
            result.append(mapping[ch])
        else:
            # 保留所有 Unicode 字母/数字
            if ch.isalnum():
                result.append(ch)
            # 保留下划线与短横
            elif ch in ('_', '-'):
                result.append(ch)
            # 保留我们映射后的中文圆括号
            elif ch in ('（', '）'):
                result.append(ch)
            else:
                # 其他一律替换下划线
                result.append('_')

    s = ''.join(result)
    # 合并连续的 '_' 或 '-'
    s = re.sub(r'[_\-]{2,}', lambda m: m.group(0)[0], s)
    # 去掉首尾的 '_' 或 '-'
    s = s.strip('_-')
    return s or '_'


def observe_blocking_func(
        func: Callable,
        *args,
        interval: float = 1.0,
        observer: Optional[Callable[[float], Any]] = None,
        **kwargs
) -> Any:
    """
    执行阻塞函数 func(*args, **kwargs)，并每隔 interval 秒通过 observer 回调报告已阻塞时长。

    :param func:     要执行的阻塞函数
    :param args:     位置参数传给 func
    :param interval: 观测间隔（秒）
    :param observer: 接受一个 float（elapsed）的回调函数，小于 0 时表示结束（如果不传入，表示通过默认的logger打印耗时）
    :param kwargs:   关键字参数传给 func
    :return: func 的返回值
    :raises: func 内部抛出的任何异常
    """
    start = time.monotonic()
    stop_event = threading.Event()

    def watcher():
        while True:
            # 如果在 interval 内被 set()，立即退出watcher
            if stop_event.wait(interval):
                break
            elapsed = time.monotonic() - start
            if observer:
                observer(elapsed)
            else:
                t_log.info(f"FUNC {func.__name__} - has blocked execution for {elapsed:.2f} seconds...")

    th = threading.Thread(target=watcher, daemon=True)
    th.start()

    try:
        result = func(*args, **kwargs)
    except Exception:
        stop_event.set()
        th.join(timeout=interval)
        traceback.print_exc()
        raise
    else:
        stop_event.set()
        th.join(timeout=interval)
        total = time.monotonic() - start
        if observer:
            # 用负值或特定标记通知结束
            observer(-total)
        else:
            t_log.info(f"FUNC {func.__name__} - Task completed, blocked execution for {total:.2f} seconds.")
        return result


def remove_empty_folder(folder_path: Union[str, Path]) -> bool:
    """
    如果给定的文件夹存在且为空，则将其移除。

    :param folder_path: 要检查并删除的文件夹路径
    :return: 如果文件夹被删除返回 True；如果文件夹不存在、非空或删除失败返回 False
    """
    folder = Path(folder_path)

    # 先检查是否真的是一个目录
    if not folder.exists():
        # logger.debug(f"路径不存在，无需删除：{folder}")
        return False

    if not folder.is_dir():
        # logger.debug(f"路径不是目录，跳过：{folder}")
        return False

    # 检查目录是否为空
    try:
        # any() 遇到第一个文件/子目录就返回 True，从而高效判断非空
        if any(folder.iterdir()):
            # logger.debug(f"目录非空，跳过删除：{folder}")
            return False
    except PermissionError as e:
        # logger.error(f"无法访问目录内容：{folder}，原因：{e}")
        return False

    # 目录存在且为空，尝试删除
    try:
        folder.rmdir()
        # logger.info(f"已删除空目录：{folder}")
        return True
    except OSError as e:
        # logger.error(f"删除目录失败：{folder}，原因：{e}")
        return False


def kill_process_tree(pid: int):
    """
    递归杀死指定 PID 的进程树（包括自身及所有后代）。
    """
    try:
        parent = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return

    # 先杀子孙
    for child in parent.children(recursive=True):
        try:
            child.kill()
        except psutil.NoSuchProcess:
            pass

    # 再杀父进程本身
    try:
        parent.kill()
    except psutil.NoSuchProcess:
        pass


def parse_time_str_to_utc(ts: str, assume_naive_utc: bool = True) -> datetime:
    """
    将 ISO-like 时间字符串解析为 timezone-aware 的 UTC datetime。
    - 支持 "2025-09-06 21:59:14.863142", "2025-09-06T21:59:14.863142Z",
      "2025-09-06T21:59:14+00:00" 等形式。
    - 若字符串带时区，则转换到 UTC 并返回 aware datetime。
    - 若字符串不带时区（naive），则:
        - 若 assume_naive_utc=True: 视为 UTC（返回 tz-aware UTC）。
        - 否则视为本地时间并转换为 UTC。
    """
    if not ts:
        raise ValueError("empty timestamp")

    s = ts.strip()

    # normalize common patterns for fromisoformat
    # replace space separator with 'T' to be more ISO-like for fromisoformat
    if "T" not in s and " " in s:
        s_norm = s.replace(" ", "T", 1)
    else:
        s_norm = s

    # handle trailing 'Z' (UTC marker)
    if s_norm.endswith("Z"):
        s_norm = s_norm[:-1] + "+00:00"

    # try fromisoformat first (fast, stdlib)
    dt: Optional[datetime] = None
    try:
        dt = datetime.fromisoformat(s_norm)
    except Exception:
        # fallback: try dateutil if available (more formats)
        try:
            from dateutil import parser as _p
            dt = _p.isoparse(s)
        except Exception:
            # final fallback: try a couple of common strptime formats (best-effort)
            fmts = ("%Y-%m-%dT%H:%M:%S.%f%z",
                    "%Y-%m-%dT%H:%M:%S%z",
                    "%Y-%m-%d %H:%M:%S.%f",
                    "%Y-%m-%d %H:%M:%S")
            for fmt in fmts:
                try:
                    dt = datetime.strptime(s, fmt)
                    break
                except Exception:
                    dt = None
    if dt is None:
        raise ValueError(f"Unrecognized datetime format: {ts!r}")

    # Normalize to timezone-aware UTC
    if dt.tzinfo is None:
        if assume_naive_utc:
            # treat naive as UTC
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            # treat naive as local time -> convert to UTC
            local_tz = datetime.now().astimezone().tzinfo
            dt = dt.replace(tzinfo=local_tz).astimezone(timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)

    return dt
