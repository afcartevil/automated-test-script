import glob
import os
from datetime import datetime, timedelta
from typing import Union, Optional

from powertrde.utils import yaml_utils
from tests.dzppt.dou3.dou3_config import Dou3Config


def calculate_time_difference(start_time_str: str, end_time_str: str) -> str:
    """
    计算两个 ISO8601 格式时间字符串之间的差值，
    返回格式化字符串 "HH:MM:SS"。

    :param start_time_str: 起始时间字符串
    :param end_time_str: 结束时间字符串
    :return: "HH:MM:SS" 格式时间差字符串
    """
    start_time = iso_to_datetime_safe(start_time_str)
    end_time = iso_to_datetime_safe(end_time_str)
    if not start_time or not end_time:
        # 兜底，兼容 None/非法字符串
        return "00:00:00"

    delta = end_time - start_time
    return format_timedelta(delta)



def calculate_time_difference_sec(total_seconds: Union[int, float, str]) -> str:
    """
    将秒数转换为标准 "HH:MM:SS" 格式字符串。
    若输入为字符串则自动转为整数。

    :param total_seconds: 时间（秒）
    :return: 格式化时间字符串
    """
    try:
        total_seconds = int(float(total_seconds))
    except Exception:
        return "00:00:00"

    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"{hours:02}:{minutes:02}:{seconds:02}"


def format_timedelta(delta: timedelta) -> str:
    """
    将 timedelta 转换为 "HH:MM:SS" 格式。
    """
    total_seconds = int(delta.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"{hours:02}:{minutes:02}:{seconds:02}"


def timedelta_to_hours(delta: Union[timedelta, float, int]) -> float:
    """
    将 timedelta 或秒数转换为小时数（浮点数）。
    :param delta: timedelta 或 秒数
    :return: 小时（float）
    """
    if isinstance(delta, timedelta):
        return delta.total_seconds() / 3600
    elif isinstance(delta, (int, float)):
        return float(delta) / 3600
    return 0.0


def safe_divide(a: float, b: float, precision: int = 2) -> float:
    """
    安全除法，避免除零错误。

    :param a: 被除数
    :param b: 除数
    :param precision: 保留小数位
    :return: 结果（若 b=0 则返回 0）
    """
    try:
        return round(a / b, precision)
    except Exception:
        return 0.0


def percent_format(value: float, total: float, precision: int = 2) -> str:
    """
    按百分比格式化输出，例如 "45.23%"。

    :param value: 分子
    :param total: 分母
    :param precision: 保留小数位
    :return: 格式化字符串
    """
    if total == 0:
        return "0.00%"
    return f"{(value / total * 100):.{precision}f}%"


def iso_to_datetime_safe(value: Optional[str]) -> Optional[datetime]:
    """
    将 ISO8601 字符串安全转换为 datetime。
    若无效则返回 None。
    """
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None

#检查bugreport文件
def check_and_find_bugreport(meta_path):
    from pathlib import Path
    import re
    import zipfile
    base_path = Path(meta_path)
    if list(base_path.glob("*bugreport*.txt")):
        return True
    try:
        bugreport_zip_paths = glob.glob(os.path.join(meta_path, "bugreport*.zip"))
        if not bugreport_zip_paths:
            current_zip = base_path.parent / 'phone_logs' / 'mobile_log1.zip'

            # 检查文件是否存在
            if not current_zip.exists():
                print(f"文件不存在: {current_zip}")
                return False

            with zipfile.ZipFile(str(current_zip.resolve()), 'r') as first_f:
                matched_zip = [f for f in first_f.namelist() if "bugreports/" in f.lower() and f.lower().endswith(".zip")]
                if not matched_zip:
                    print("未找到bugreports相关的zip文件")
                    return False

                first_f.extract(matched_zip[0], str(base_path.resolve()))
                # 移动文件到目标位置
                extracted_path = os.path.join(str(base_path.resolve()), matched_zip[0])
                zip_filename = os.path.basename(matched_zip[0])
                bugreport_zip_path = os.path.join(str(base_path.resolve()), zip_filename)

                import shutil
                shutil.move(extracted_path, bugreport_zip_path)

                # 删除空的bugreports文件夹
                bugreports_dir = os.path.join(str(base_path.resolve()), "bugreports")
                if os.path.exists(bugreports_dir):
                    os.rmdir(bugreports_dir)

        else:
            bugreport_zip_path = bugreport_zip_paths[0]

        with zipfile.ZipFile(bugreport_zip_path, 'r') as zf:
            matched_txts = [f for f in zf.namelist() if re.search(r"bugreport.*\.txt", f)]
            with zf.open(matched_txts[0], "r") as src_file:
                with open(os.path.join(meta_path, 'bugreport.txt'), 'wb') as wf:
                    for chunk in iter(lambda: src_file.read(1024 * 1024), b''):
                        wf.write(chunk)
        return True
    except:
        return False

#从配置文件中获取归一化亮灭屏时长
def get_normalized_on_off_hours(area:str,screen_time_mapping):
    uc = Dou3Config.get_instance()
    cfg = uc.get_config('normalized_screen_on_and_off')

    # 优先使用配置的 {on, off}
    if isinstance(cfg, dict):
        on = cfg.get('on')
        off = cfg.get('off')
        if on is not None and off is not None:
            try:
                return float(on), float(off)
            except Exception:
                pass  # 配置存在但数值异常则继续走默认
    # 未配置时使用默认
    d = screen_time_mapping.get(area)
    return float(d.get('亮屏时长', 4)), float(d.get('灭屏时长', 5.35))


#从文件中获取电池容量
def _get_battery_capacity(meta_report_dir: str) -> int:
    session_process_report_file = os.path.join(meta_report_dir, 'session_process_report.yaml')

    if os.path.exists(session_process_report_file):
        process_dict = yaml_utils.read_yaml(session_process_report_file)

        try:
            # 使用 get 方法获取值，避免直接访问导致 KeyError
            battery_capacity = process_dict.get('device_info', {}).get('other_infos', {}).get('battery_capacity', 0)

            # 确保返回值是数值类型，否则返回默认值 0
            return int(battery_capacity) if isinstance(battery_capacity, (int, float)) else 0
        except Exception as e:
            # 可选：记录异常信息
            pass

    # 如果文件不存在或发生异常，返回默认值 0
    return 0


#从current sheet页获取字段duration_sec 字段数据
def get_duration_sec_by_current_sheet(screen_on_and_off_dict:dict):
    on_secs = 0.0
    off_secs = 0.0
    for start, end, screen_status, c, v in screen_on_and_off_dict:
        dur = (end - start).total_seconds()
        if screen_status == 'on':
            on_secs += dur
        elif screen_status == 'off':
            off_secs += dur
    return on_secs,off_secs
