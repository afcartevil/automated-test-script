"""
bugreport_parser.py

一个专业的 Bugreport 解析工具，专注于 Battery History 部分的解析。
功能包括：
  - 提取屏幕灭屏 (OFF) → 点亮 (ON) 的时间区间
  - 将区间保存到 YAML
  - 计算指定时间段内或全量的灭屏/点亮/总时长

用法示例：
    from bugreport_parser import BugreportParser
    import datetime

    # 实例化
    parser = BugreportUtils("bugreport-2025-06-06.txt"，gap_time_to_pc)

    # 1. 提取所有灭屏→点亮区间
    intervals = parser.get_screen_intervals()

    # 2. 保存到 YAML
    parser.save_screen_intervals_to_yaml("screen_intervals.yaml", intervals)

    # 3. 计算指定时间段的总灭屏/点亮/总时长
    start = datetime.datetime(2025, 6, 5, 20, 0, 0)
    end   = datetime.datetime(2025, 6, 6, 2, 0, 0)
    durations = parser.get_total_screen_durations(start, end)
    # durations == {'total_off': timedelta(...), 'total_on': timedelta(...), 'total': timedelta(...)}

    # 4. 计算全量灭屏/点亮/总时长
    durations_all = parser.get_total_screen_durations()
"""

import re
import datetime
from datetime import datetime

import yaml
from typing import List, Tuple, Optional, Dict
import datetime


class BugreportParser:
    """
    Bugreport 解析工具，针对 Battery History 中的屏幕状态 (OFF/ON) 事件进行提取与分析。

    Attributes:
        bugreport_path (str): 本地 Bugreport 文本文件路径
        reset_time (datetime.datetime): Battery History 中的 RESET:TIME 对应的绝对时间
        raw_events (List[Tuple[datetime.datetime, str]]): 原始 OFF/ON 事件列表（已排序）
        intervals (List[Tuple[datetime.datetime, Optional[datetime.datetime]]]):
            配对后的灭屏→点亮区间列表 (off_time, on_time)，若 on_time=None 表示未闭合
    """

    def __init__(self, bugreport_path: str, gap_time_to_pc: float = 0.0):
        """
        :param bugreport_path: Bugreport 文本文件路径
        """
        self.bugreport_path = bugreport_path
        self.reset_time: Optional[datetime.datetime] = None
        self.raw_events: List[Tuple[datetime.datetime, str]] = []
        self.intervals: List[Tuple[datetime.datetime, Optional[datetime.datetime]]] = []
        self.gap_time_to_pc = datetime.timedelta(seconds=gap_time_to_pc)

        self._parse_battery_history()

    @staticmethod
    def _parse_duration_to_timedelta(duration_str: str) -> datetime.timedelta:
        """
        将类似 "12d21h40m32s234ms"、"4h17m48s90ms"、"30s540ms" 等字符串转换为 timedelta。
        支持 d, h, m, s, ms 单位。
        """
        pattern = re.compile(
            r'(?:(\d+)d)?'      # 组1：天
            r'(?:(\d+)h)?'      # 组2：小时
            r'(?:(\d+)m)?'      # 组3：分钟
            r'(?:(\d+)s)?'      # 组4：秒
            r'(?:(\d+)ms)?'     # 组5：毫秒
        )
        m = pattern.fullmatch(duration_str)
        if not m:
            return datetime.timedelta()
        days = int(m.group(1)) if m.group(1) else 0
        hours = int(m.group(2)) if m.group(2) else 0
        minutes = int(m.group(3)) if m.group(3) else 0
        seconds = int(m.group(4)) if m.group(4) else 0
        milliseconds = int(m.group(5)) if m.group(5) else 0
        return datetime.timedelta(
            days=days, hours=hours, minutes=minutes,
            seconds=seconds, milliseconds=milliseconds
        )

    def _parse_battery_history(self):
        """
        内部方法：读取 Bugreport，解析 Battery History 段，提取 RESET:TIME 及 OFF/ON 事件，生成 intervals 列表。
        """
        with open(self.bugreport_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()

        # 1. 定位 "Battery History" 段
        hist_start_idx: Optional[int] = None
        for idx, line in enumerate(lines):
            if line.strip().startswith("Battery History"):
                hist_start_idx = idx
                break
        if hist_start_idx is None:
            raise ValueError("未找到 'Battery History' 段落，请检查 Bugreport 内容。")

        # 2. 查找 RESET:TIME
        self.reset_time = None
        reset_idx: Optional[int] = None
        reset_pattern = re.compile(r"RESET:TIME:\s*(\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2})")
        time_pattern = re.compile(r"TIME:\s*(\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2})")
        for i in range(hist_start_idx + 1, len(lines)):
            m = reset_pattern.search(lines[i])
            if m:
                ts = m.group(1)  # e.g. "2025-06-05-19-25-08"
                parts = ts.split('-')
                try:
                    self.reset_time = datetime.datetime(
                        year=int(parts[0]),
                        month=int(parts[1]),
                        day=int(parts[2]),
                        hour=int(parts[3]),
                        minute=int(parts[4]),
                        second=int(parts[5])
                    )
                except ValueError:
                    raise ValueError(f"无法解析 RESET:TIME 时间戳：{ts}")
                reset_idx = i
                break

        if self.reset_time is None:
            for i in range(hist_start_idx + 1, len(lines)):
                line = lines[i]
                m = time_pattern.search(line)
                if m:
                    ts = m.group(1)
                    parts = ts.split('-')
                    try:
                        self.reset_time = datetime.datetime(
                            year=int(parts[0]),
                            month=int(parts[1]),
                            day=int(parts[2]),
                            hour=int(parts[3]),
                            minute=int(parts[4]),
                            second=int(parts[5])
                        )
                    except ValueError:
                        raise ValueError(f"无法解析 TIME 时间戳：{ts}")
                    reset_idx = i
                    break

        if self.reset_time is None:
            raise ValueError("未找到 RESET:TIME 或 TIME 行。")

        # 3. 从 reset_idx+1 行开始解析 Battery History 条目
        # 更严谨的 Battery History 行前缀匹配，包括 1d2h3m4s5ms 这种组合
        prefix_pattern = re.compile(r"^\s*(\+?(?:\d+d)?(?:\d+h)?(?:\d+m)?(?:\d+s)?(?:\d+ms)?)\b")
        idx = reset_idx + 1
        raw_events: List[Tuple[datetime.datetime, str]] = []

        while idx < len(lines):
            line = lines[idx]
            # Battery History 段以缩进开始，遇到不再缩进(新段落)则结束
            if not (line.startswith(" ") or line.startswith("\t")):
                if re.match(r"^[A-Za-z]", line.strip()):
                    break
            stripped = line.strip()
            if not stripped:
                idx += 1
                continue

            # 首先检查是否为OS16格式 (时间戳格式: "06-10 18:22:06.102")
            timestamp_match = re.match(r"^\s*(\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})", stripped)
            if timestamp_match:
                # OS16格式处理
                timestamp_str = timestamp_match.group(1)
                try:
                    # 解析时间戳，使用reset_time的年份
                    year = self.reset_time.year
                    full_timestamp_str = f"{year}-{timestamp_str}"
                    absolute_ts = datetime.datetime.strptime(full_timestamp_str, "%Y-%m-%d %H:%M:%S.%f")

                    # 校准时间
                    absolute_ts = absolute_ts

                    # 检查屏幕事件
                    if "-screen" in stripped:
                        raw_events.append((absolute_ts, "OFF"))
                    elif "+screen" in stripped:
                        if raw_events and raw_events[-1][1] == "OFF":
                            raw_events.append((absolute_ts, "ON"))

                except ValueError as e:
                    print(f"解析OS16时间戳失败: {timestamp_str}, 错误: {e}")
            else:
                # OS15格式处理 (保持原有逻辑完全不变)
                # 提取 prefix，例如 "0" 或 "+11m56s388ms"
                m_pref = prefix_pattern.match(stripped)
                if not m_pref:
                    idx += 1
                    continue
                prefix = m_pref.group(1)

                # 解析 prefix 为相对 RESET 的偏移
                if prefix.startswith("+"):
                    delta = self._parse_duration_to_timedelta(prefix[1:])
                else:
                    delta = datetime.timedelta()  # prefix == "0"

                # 校准时间
                absolute_ts = self.reset_time + delta
                # 仅当最近有未配对的 OFF 才记录 ON，避免 RESET 处 "+screen" 误判
                if "-screen" in stripped:
                    raw_events.append((absolute_ts, "OFF"))
                elif "+screen" in stripped:
                    if raw_events and raw_events[-1][1] == "OFF":
                        raw_events.append((absolute_ts, "ON"))

            idx += 1

        # 4. raw_events 排序并存储
        raw_events.sort(key=lambda x: x[0])
        self.raw_events = raw_events

        # 5. 配对 OFF->ON 得到 self.intervals
        intervals: List[Tuple[datetime.datetime, Optional[datetime.datetime]]] = []
        off_time: Optional[datetime.datetime] = None

        for ts, state in raw_events:
            if state == "OFF":
                if off_time is None:
                    off_time = ts
            elif state == "ON" and off_time is not None:
                intervals.append((off_time, ts))
                off_time = None

        # 若最后一次 OFF 后没对应 ON，则添加未闭合区间
        if off_time is not None:
            intervals.append((off_time, None))

        self.intervals = intervals

    def get_screen_intervals(
        self,
        start_time: Optional[datetime.datetime] = None,
        end_time:   Optional[datetime.datetime] = None,
    ):
        """
        获取屏幕灭屏(OFF)→点亮(ON) 的时间区间列表。
        :param start_time: 可选开始时间（闭区间），或 None
        :param end_time:   可选结束时间（闭区间），或 None
        :return: List of (off_time, on_time)。若 on_time=None 表示未闭合区间。
        """
        if start_time is None and end_time is None:
            return list(self.intervals)

        clipped: List[Tuple[datetime.datetime, Optional[datetime.datetime]]] = []
        for off_ts, on_ts in self.intervals:
            # 整个区间在查询范围右侧
            if end_time is not None and off_ts > end_time:
                continue
            # 整个区间在查询范围左侧
            if on_ts is not None and start_time is not None and on_ts < start_time:
                continue

            clipped_off = off_ts if start_time is None else max(off_ts, start_time)
            if on_ts is None:
                clipped_on = None
            else:
                if end_time is None:
                    clipped_on = on_ts
                else:
                    clipped_on = on_ts if on_ts <= end_time else end_time

            clipped.append((clipped_off, clipped_on))

        return clipped

    def analyze_screen_intervals(self,
            start_time: Optional[datetime.datetime] = None,
            end_time: Optional[datetime.datetime] = None,
            min_off_duration: datetime.timedelta = datetime.timedelta(seconds=10)
    ) -> Dict[str, any]:
        """
        综合分析屏幕状态区间，包括计算亮屏区间、时长统计(传入的是主机时间，传出的也应该是主机时间，所以需要减去gap再加上gap)

        :param start_time: 会话开始时间
        :param end_time: 会话结束时间
        :param min_off_duration: 有效灭屏时间段取消无效时间段
        :return: 包含亮屏区间、时长统计等的完整分析结果 区间列表 （start, end, screen_state）
        """

        # 1. 确定 period_start, period_end
        if start_time is not None:
            period_start = start_time - self.gap_time_to_pc
        else:
            # 未传 start_time，则使用 reset_time
            period_start = self.reset_time  # type: ignore

        if end_time is not None:
            period_end = end_time - self.gap_time_to_pc
        else:
            # 未传 end_time，则使用最后一个 raw_event 时间
            if not self.raw_events:
                return {'total_off': datetime.timedelta(), 'total_on': datetime.timedelta(),
                        'total': datetime.timedelta(), 'final_intervals': []}
            period_end = self.raw_events[-1][0]
        # 若 period_end <= period_start，返回全为 0
        if period_end <= period_start:
            zero = datetime.timedelta()
            return {'total_off': zero, 'total_on': zero, 'total': zero, 'final_intervals': []}

        # 2. 获取区间列表
        screen_off_intervals = self.get_screen_intervals(period_start, period_end)
        total_off = 0.0
        total_on = 0.0
        total = 0.0

        # 3. 过滤少于min_off_duration的灭屏区间
        filtered_off_intervals = []
        for i, (off_ts, on_ts) in enumerate(screen_off_intervals):
            if on_ts is None:
                # 未闭合区间，检查从off到period_end的持续时间
                duration = period_end - off_ts
            else:
                # 闭合区间，计算实际持续时间
                duration = on_ts - off_ts

            # 只保留大于等于min_off_duration的灭屏区间
            if duration > min_off_duration:
                filtered_off_intervals.append((off_ts, on_ts))

        # 4.添加亮屏区间（从当前位置到灭屏开始）
        final_intervals = []
        cur = period_start

        for off, on in filtered_off_intervals:
            if cur < off:
                final_intervals.append((cur+self.gap_time_to_pc, off+self.gap_time_to_pc, "on"))

            # 添加灭屏区间
            end_time_off = on if on else period_end
            final_intervals.append((off+self.gap_time_to_pc, end_time_off+self.gap_time_to_pc, "off"))

            # 更新当前位置到灭屏结束
            cur = end_time_off

        # 最后尾巴
        if cur < period_end:
            final_intervals.append((cur+self.gap_time_to_pc, period_end+self.gap_time_to_pc, "on"))

        # 5. 计算时长统计
        total_off = datetime.timedelta()
        for off_ts, on_ts in filtered_off_intervals:
            if on_ts is None:
                total_off += (period_end - off_ts)
            else:
                total_off += (on_ts - off_ts)

        total = period_end - period_start
        total_on = total - total_off
        if total_on < datetime.timedelta():
            total_on = datetime.timedelta()
        # （先排序，再返回）
        final_intervals.sort(key=lambda x: x[0])

        return {'total_off': total_off, 'total_on': total_on, 'total': total, 'final_intervals': final_intervals}
    def save_screen_intervals_to_yaml(
        self,
        yaml_path: str,
        intervals: Optional[List[Tuple[datetime.datetime, Optional[datetime.datetime]]]] = None
    ):
        """
        将指定的屏幕区间写入 YAML 文件，如果不传 intervals，则导出 self.intervals。
        :param yaml_path: 输出 YAML 文件路径
        :param intervals: 可选区间列表
        """
        to_save = intervals if intervals is not None else self.intervals
        data = [
            {'off': off_ts.isoformat(), 'on': on_ts.isoformat() if on_ts else None}
            for off_ts, on_ts in to_save
        ]
        with open(yaml_path, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, allow_unicode=True)

    def get_total_screen_durations(
        self,
        start_time: Optional[datetime.datetime] = None,
        end_time:   Optional[datetime.datetime] = None
    ) -> Dict[str, datetime.timedelta]:
        """
        计算指定时间段（或全量）的总灭屏时长 (total_off)、总点亮时长 (total_on) 与总时长 (total)。

        逻辑：
          1. 获取裁剪后的所有 OFF→ON 区间 (get_screen_intervals)。
          2. 确定 period_start, period_end：
             - period_start = start_time if 提供，否则 reset_time
             - period_end   = end_time   if 提供，否则最后一个事件时间
          3. 计算 total_off = sum( on_ts - off_ts ) 对每个区间 (若 on_ts=None，则以 period_end)
          4. total = period_end - period_start
          5. total_on = total - total_off

        :param start_time: 可选开始时间，或 None
        :param end_time:   可选结束时间，或 None
        :return: {'total_off': timedelta, 'total_on': timedelta, 'total': timedelta}
        """
        # 1. 获取区间列表
        intervals = self.get_screen_intervals(start_time, end_time)

        # 2. 确定 period_start, period_end
        if start_time is not None:
            period_start = start_time - self.gap_time_to_pc
        else:
            # 未传 start_time，则使用 reset_time
            period_start = self.reset_time # type: ignore

        if end_time is not None:
            period_end = end_time - self.gap_time_to_pc
        else:
            # 未传 end_time，则使用最后一个 raw_event 时间
            if not self.raw_events:
                return {'total_off': datetime.timedelta(), 'total_on': datetime.timedelta(), 'total': datetime.timedelta()}
            period_end = self.raw_events[-1][0]

        # 若 period_end <= period_start，返回全为 0
        if period_end <= period_start:
            zero = datetime.timedelta()
            return {'total_off': zero, 'total_on': zero, 'total': zero}

        # 3. 计算 total_off
        total_off = datetime.timedelta()
        for off_ts, on_ts in intervals:
            if on_ts is None:
                total_off += (period_end - off_ts)
            else:
                total_off += (on_ts - off_ts)

        # 4. 总时长
        total = period_end - period_start

        # 5. 总点亮时长
        total_on = total - total_off
        if total_on < datetime.timedelta():
            total_on = datetime.timedelta()

        return {'total_off': total_off, 'total_on': total_on, 'total': total}

def load_yaml_data(yaml_path: str):
    import yaml
    import os
    try:
        with open(yaml_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        gap_time_to_pc = float(data.get('gap_time_to_pc', 0.0))
        start_time = datetime.datetime.fromisoformat(data.get('start_time', 0.0))
        ## session_process_report.yaml 文件中的end_time都为null, 检查下是哪里出错了
        end_time = datetime.datetime.fromisoformat(data.get('end_time', 0.0))
        return gap_time_to_pc, start_time, end_time
    except Exception as e:
        print(f"[警告] 读取 gap_time_to_pc 失败，默认使用 0.0 秒。原因: {e}")
        return 0.0, 0.0, 0.0

if __name__ == "__main__":
    # 读取时间差
    gap_yaml_path = r"E:\20250606-201646_X6730_15.1.2.011_SN153113755M000071_PowerMonitor\meta_report\session_total_report.yaml"
    gap_time_to_pc, start_time, end_time = load_yaml_data(gap_yaml_path)

    # 示例：实例化并获取区间、总时长
    bugreport_file = r"E:\20250606-201646_X6730_15.1.2.011_SN153113755M000071_PowerMonitor\meta_report\bugreport-X6730-IN-AP3A.240905.015.A2-2025-06-07-05-40-34.txt"

    parser = BugreportParser(bugreport_file, gap_time_to_pc)

    # # 1. 全量区间
    # screen_off_intervals = parser.get_screen_intervals()
    # # print(f"灭屏区间数: {len(all_intervals)}")
    # # for i, (start, end) in enumerate(all_intervals):
    # #     print(f"[灭屏#{i + 1}] {start} → {end}，持续: {(end - start).total_seconds()} 秒")
    #
    # parser.save_screen_intervals_to_yaml(r"E:\20250606-201646_X6730_15.1.2.011_SN153113755M000071_PowerMonitor\save.yaml", screen_off_intervals)
    #
    # # 2. 指定时段总时长 需要手动处理 self.gap_time_to_pc
    # # start_time = datetime.datetime(2025, 6, 5, 20, 0, 0)
    # # end_time = datetime.datetime(2025, 6, 6, 2, 0, 0)
    # durations = parser.get_total_screen_durations(start_time, end_time)
    # # print(f"指定区间总灭屏时长：{durations['total_off']}, 总点亮时长：{durations['total_on']}, 总时长：{durations['total']}")

    # 3. 全量总时长
    durations_all = parser.analyze_screen_intervals()
    # print(f"全量总灭屏时长：{durations_all['total_off']}, 全量总点亮时长：{durations_all['total_on']}, 全量总时长：{durations_all['total']}")
    print(f"所有区间数: {len(durations_all['final_intervals'])}")
    for i, (start, end, s) in enumerate(durations_all['final_intervals']):
        print(f"[{s}: {i + 1}] {start} → {end}，持续: {(end - start).total_seconds()} 秒")
