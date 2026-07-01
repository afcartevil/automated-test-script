from dataclasses import dataclass
from datetime import datetime, timedelta
import struct
import multiprocessing
import os
from typing import Optional, Union, Tuple, List
from multiprocessing import dummy



@dataclass
class PT5Header:
    headSize: int
    fileName: str
    batterySize: int
    timezoneFlag: int
    captureDate: datetime
    captureEndDate: datetime
    duration: float
    serialNumber: str
    calibrationStatus: int
    voutSetting: int
    voutValue: float
    hardwareRate: int
    softwareRate: float
    powerField: int
    currentField: int
    voltageField: int
    captureSetting: str
    swVersion: str
    runMode: int
    exitCode: int
    totalCount: int
    statusOffset: int
    statusSize: int
    sampleOffset: int
    sampleSize: int
    initialMainVoltage: int
    initialUsbVoltage: int
    initialAuxVoltage: int
    captureDataMask: int
    sampleCount: int
    missingCount: int
    sumMainVoltage: float
    sumMainCurrent: float
    sumMainPower: float
    sumUsbVoltage: float
    sumUsbCurrent: float
    sumUsbPower: float
    sumAuxVoltage: float
    sumAuxCurrent: float
    sumAuxPower: float


def _process_chunk(args):
    """
    读取 filename 中从 offset 开始的 n_samples 样本数据，
    每个样本6字节（格式 '<iH'：电流为 int32, 电压为 uint16）。
    累加当前和电压（跳过缺失数据），返回 (sum_current, sum_voltage, count, samples_data)。
    """
    filename, offset, n_samples, need_samples_data = args
    samples_data = None
    sample_size = 6
    fmt = '<iH'
    total_current = 0
    total_voltage = 0
    valid_count = 0
    with open(filename, 'rb') as f:
        f.seek(offset)
        for i in range(n_samples):
            data = f.read(sample_size)
            if len(data) != sample_size:
                break
            current, voltage = struct.unpack(fmt, data)
            if current == 0x8001 or voltage == 0xFFFF:
                continue
            total_current += current
            total_voltage += voltage
            valid_count += 1
            if need_samples_data:
                samples_data = (offset + i, total_current, total_voltage)
    return total_current, total_voltage, valid_count, samples_data


class PT5Reader:
    """
    采用多进程并行方案处理pt5大文件，避免将全部样本加载内存。
    """

    def __init__(self, filename: Union[str, os.PathLike], timezone_delta: timedelta):
        self.filename = filename
        self.header: Optional[PT5Header] = None
        self.timezone_delta = timezone_delta
        self._file_size = None
        self.time_scale = 0.99847
        self.load_header()

    def load_header(self):
        # 只读取 Header 部分
        with open(self.filename, 'rb') as f:
            header_bytes = f.read(212)
        header = {'headSize': struct.unpack_from('<I', header_bytes, 0)[0],
                  'Name': struct.unpack_from('20s', header_bytes, 4)[0].decode('ascii', errors='ignore').strip('\x00'),
                  'batterySize': struct.unpack_from('<I', header_bytes, 24)[0]}
        # 解析 captureDate（取低63位）
        raw_date = struct.unpack_from('<q', header_bytes, 28)[0]
        raw_date_utc = raw_date & 0x7FFFFFFFFFFFFFFF
        timezoneFlag = (raw_date >> 63) & 1
        capture_date = datetime(1, 1, 1) + timedelta(microseconds=raw_date_utc / 10)
        if timezoneFlag:
            capture_date += self.timezone_delta

        header['timezoneFlag'] = timezoneFlag
        header['captureDate'] = capture_date
        header['serialNumber'] = struct.unpack_from('20s', header_bytes, 36)[0].decode('ascii', errors='ignore').strip(
            '\x00')
        header['calibrationStatus'] = struct.unpack_from('<I', header_bytes, 56)[0]
        header['voutSetting'] = struct.unpack_from('<I', header_bytes, 60)[0]
        header['voutValue'] = struct.unpack_from('<f', header_bytes, 64)[0]
        header['hardwareRate'] = struct.unpack_from('<I', header_bytes, 68)[0]
        header['softwareRate'] = struct.unpack_from('<f', header_bytes, 72)[0]
        header['powerField'] = struct.unpack_from('<I', header_bytes, 76)[0]
        header['currentField'] = struct.unpack_from('<I', header_bytes, 80)[0]
        header['voltageField'] = struct.unpack_from('<I', header_bytes, 84)[0]
        header['captureSetting'] = struct.unpack_from('30s', header_bytes, 88)[0].decode('ascii',
                                                                                         errors='ignore').strip('\x00')
        header['swVersion'] = struct.unpack_from('10s', header_bytes, 118)[0].decode('ascii', errors='ignore').strip(
            '\x00')
        header['runMode'] = struct.unpack_from('<I', header_bytes, 128)[0]
        header['exitCode'] = struct.unpack_from('<I', header_bytes, 132)[0]
        header['totalCount'] = struct.unpack_from('<Q', header_bytes, 136)[0]
        header['statusOffset'] = struct.unpack_from('<H', header_bytes, 144)[0]
        header['statusSize'] = struct.unpack_from('<H', header_bytes, 146)[0]
        header['sampleOffset'] = struct.unpack_from('<H', header_bytes, 148)[0]
        header['sampleSize'] = struct.unpack_from('<H', header_bytes, 150)[0]
        header['initialMainVoltage'] = struct.unpack_from('<H', header_bytes, 152)[0]
        header['initialUsbVoltage'] = struct.unpack_from('<H', header_bytes, 154)[0]
        header['initialAuxVoltage'] = struct.unpack_from('<H', header_bytes, 156)[0]
        header['captureDataMask'] = struct.unpack_from('<H', header_bytes, 158)[0]
        header['sampleCount'] = struct.unpack_from('<Q', header_bytes, 160)[0]
        header['missingCount'] = struct.unpack_from('<Q', header_bytes, 168)[0]
        header['sumMainVoltage'] = struct.unpack_from('<f', header_bytes, 176)[0]
        header['sumMainCurrent'] = struct.unpack_from('<f', header_bytes, 180)[0]
        header['sumMainPower'] = struct.unpack_from('<f', header_bytes, 184)[0]
        header['sumUsbVoltage'] = struct.unpack_from('<f', header_bytes, 188)[0]
        header['sumUsbCurrent'] = struct.unpack_from('<f', header_bytes, 192)[0]
        header['sumUsbPower'] = struct.unpack_from('<f', header_bytes, 196)[0]
        header['sumAuxVoltage'] = struct.unpack_from('<f', header_bytes, 200)[0]
        header['sumAuxCurrent'] = struct.unpack_from('<f', header_bytes, 204)[0]
        header['sumAuxPower'] = struct.unpack_from('<f', header_bytes, 208)[0]
        # 计算采样时长与结束时间
        header['duration'] = header['totalCount'] / header['hardwareRate']
        header['duration'] /= self.time_scale
        header['captureEndDate'] = header['captureDate'] + timedelta(seconds=header['duration'])
        self.header = PT5Header(
            headSize=header['headSize'],
            fileName=header['Name'],
            batterySize=header['batterySize'],
            timezoneFlag=header['timezoneFlag'],
            captureDate=header['captureDate'],
            captureEndDate=header['captureEndDate'],
            duration=header['duration'],
            serialNumber=header['serialNumber'],
            calibrationStatus=header['calibrationStatus'],
            voutSetting=header['voutSetting'],
            voutValue=header['voutValue'],
            hardwareRate=header['hardwareRate'],
            softwareRate=header['softwareRate'],
            powerField=header['powerField'],
            currentField=header['currentField'],
            voltageField=header['voltageField'],
            captureSetting=header['captureSetting'],
            swVersion=header['swVersion'],
            runMode=header['runMode'],
            exitCode=header['exitCode'],
            totalCount=header['totalCount'],
            statusOffset=header['statusOffset'],
            statusSize=header['statusSize'],
            sampleOffset=header['sampleOffset'],
            sampleSize=header['sampleSize'],
            initialMainVoltage=header['initialMainVoltage'],
            initialUsbVoltage=header['initialUsbVoltage'],
            initialAuxVoltage=header['initialAuxVoltage'],
            captureDataMask=header['captureDataMask'],
            sampleCount=header['sampleCount'],
            missingCount=header['missingCount'],
            sumMainVoltage=header['sumMainVoltage'],
            sumMainCurrent=header['sumMainCurrent'],
            sumMainPower=header['sumMainPower'],
            sumUsbVoltage=header['sumUsbVoltage'],
            sumUsbCurrent=header['sumUsbCurrent'],
            sumUsbPower=header['sumUsbPower'],
            sumAuxVoltage=header['sumAuxVoltage'],
            sumAuxCurrent=header['sumAuxCurrent'],
            sumAuxPower=header['sumAuxPower']
        )
        # 同时获取文件总大小
        self._file_size = os.path.getsize(self.filename)
        return self

    def _iter_chunks(self, start_sample=0, n_samples=None):
        total_samples = self.header.totalCount
        if n_samples is None:
            n_samples = total_samples - start_sample
        sample_offset = self.header.sampleOffset + start_sample * self.header.sampleSize
        remaining = n_samples
        # 动态确定分块方案：这里按系统 CPU 数量分区，但保证每个任务的样本数不少于 1e6
        min_chunk = 1_000_000
        nproc = min(multiprocessing.cpu_count(), 16, total_samples // min_chunk + 1)
        chunk = total_samples // nproc
        while remaining > 0:
            cur_chunk = min(chunk, remaining)
            yield sample_offset, cur_chunk
            sample_offset += cur_chunk * self.header.sampleSize
            remaining -= cur_chunk

    def _compute_average(self, start_sample=0, n_samples=None, need_samples_data=False):
        pool = multiprocessing.dummy.Pool()
        tasks = []
        for offset, chunk in self._iter_chunks(start_sample, n_samples):
            tasks.append((self.filename, offset, chunk, need_samples_data))
        results = pool.map(_process_chunk, tasks)
        pool.close()
        pool.join()
        total_current = sum(r[0] for r in results)
        total_voltage = sum(r[1] for r in results)
        total_count = sum(r[2] for r in results)
        total_samples_data = None
        if need_samples_data:
            total_samples_data = []
            for r in results:
                if r[3]:
                    total_samples_data.extend(r[3])
            total_samples_data.sort(key=lambda x: x[0])
        return total_current, total_voltage, total_count, total_samples_data

    def get_overall_average(self, need_samples_data=False):
        """
        计算整个样本区间的平均电流和平均电压，单位分别转换为 mA 和 V
        """
        total_current, total_voltage, count, samples_data = self._compute_average(need_samples_data=need_samples_data)
        if count == 0:
            return None, None, samples_data
        avg_current_mA = total_current / count / 1000.0
        avg_voltage_V = total_voltage / count * 500e-6
        return avg_current_mA, avg_voltage_V, samples_data

    def time_index_range(self, start_time: datetime, end_time: datetime) -> (int, int):
        fs = self.header.hardwareRate
        delta_start = (start_time - self.header.captureDate).total_seconds()
        delta_end = (end_time - self.header.captureDate).total_seconds()
        start_index = int(delta_start * fs * self.time_scale)
        end_index = int(delta_end * fs * self.time_scale)
        return start_index, end_index

    def relative_time_index_range(self, start_time_in_seconds: float, end_time_in_seconds: float) -> (int, int):
        fs = self.header.hardwareRate
        start_index = int(start_time_in_seconds * fs * self.time_scale)
        end_index = int(end_time_in_seconds * fs * self.time_scale)
        return start_index, end_index

    def get_average_current_voltage(self, start_time_or_relative_start_seconds: Union[datetime, float],
                                    end_time_or_relative_end_seconds: Union[datetime, float],
                                    auto_correction_time=False):
        """
        计算指定时间段内的平均电流和电压
        """
        if isinstance(start_time_or_relative_start_seconds, datetime):
            start_idx, end_idx = self.time_index_range(start_time_or_relative_start_seconds,
                                                       end_time_or_relative_end_seconds)
        else:
            start_idx, end_idx = self.relative_time_index_range(start_time_or_relative_start_seconds,
                                                                end_time_or_relative_end_seconds)
        if auto_correction_time:
            if start_idx < 0:
                start_idx = 0
            if end_idx > self.header.totalCount:
                end_idx = self.header.totalCount
        n_samples = end_idx - start_idx
        if n_samples <= 0 or start_idx < 0 or end_idx > self.header.totalCount:
            raise ValueError("指定时间段超出采样范围")
        total_current, total_voltage, count, _ = self._compute_average(start_sample=start_idx, n_samples=n_samples)
        if count == 0:
            return None, None
        avg_current_mA = total_current / count / 1000.0
        avg_voltage_V = total_voltage / count * 500e-6
        return avg_current_mA, avg_voltage_V

    def extract_time_slice(self, start_time_or_relative_start_seconds: Union[datetime, float],
                           end_time_or_relative_end_seconds: Union[datetime, float], output_filename: str,
                           auto_correction_time=False):
        """
        从当前 PT5 文件中截取指定时间段的样本数据，生成一个新的完整 PT5 文件。
        处理过程：
          1. 根据 start_time_or_relative_start_seconds, end_time_or_relative_end_seconds 计算对应样本索引区间 [start_idx, end_idx)。
          2. 计算截取的样本数。
          3. 读取原文件中从 0 到 sampleOffset 的所有字节（前置区域，包括 Header、Status Packet 等）。
          4. 读取截取的样本数据区域字节。
          5. 修改 Header 中相关字段（captureDate、totalCount、sampleCount、missingCount）：
             - captureDate 更新为截取区域的起始时间（即 start_time）。
             - totalCount 和 sampleCount 更新为截取的样本数。
             - missingCount 置 0。
             - 同时更新 duration 与 captureEndDate（duration = n_samples / hardwareRate）。
          6. 将更新后的前置区域和新的样本数据写入到输出文件中。
        """
        sample_size = self.header.sampleSize  # 应为6字节
        if isinstance(start_time_or_relative_start_seconds, datetime):
            start_idx, end_idx = self.time_index_range(start_time_or_relative_start_seconds,
                                                       end_time_or_relative_end_seconds)
        else:
            start_idx, end_idx = self.relative_time_index_range(start_time_or_relative_start_seconds,
                                                                end_time_or_relative_end_seconds)
        if auto_correction_time:
            if start_idx < 0:
                start_idx = 0
            if end_idx > self.header.totalCount:
                end_idx = self.header.totalCount
        n_samples_extracted = end_idx - start_idx
        if n_samples_extracted <= 0 or start_idx < 0 or end_idx > self.header.totalCount:
            raise ValueError("指定时间段超出采样范围")

        with open(self.filename, 'rb') as f:
            original_header_bytes = bytearray(f.read(212))
            middle_bytes = f.read(self.header.sampleOffset - 212)
            f.seek(self.header.sampleOffset + start_idx * sample_size)
            sample_data = f.read(n_samples_extracted * sample_size)

        # 准备更新 header：以原 header 的前212字节为基准（Header区固定长度为212字节）
        # 更新 captureDate：新文件的 captureDate 设置为 start_time，转换为 .NET Ticks格式
        # 读取原始 captureDate 的 ticks（已经去除符号位）
        original_ticks = struct.unpack_from('<q', original_header_bytes, 28)[0] & 0x7FFFFFFFFFFFFFFF
        # 计算传入 start_time 与原始 captureDate 的差值（以秒为单位），转换为 ticks（每 tick = 100 纳秒）
        if isinstance(start_time_or_relative_start_seconds, datetime):
            delta = start_time_or_relative_start_seconds - self.header.captureDate
        else:
            delta = timedelta(seconds=start_time_or_relative_start_seconds)
        if self.header.timezoneFlag:
            delta += self.timezone_delta
        delta_ticks = int(delta.total_seconds() * 1e7)
        # 新的 ticks 就等于原始 ticks 加上差值
        new_ticks = (original_ticks + delta_ticks) & 0x7FFFFFFFFFFFFFFF
        struct.pack_into('<q', original_header_bytes, 28, new_ticks)
        # 更新 totalCount (offset 136) 为 n_samples_extracted
        struct.pack_into('<Q', original_header_bytes, 136, n_samples_extracted)
        # 更新 missingCount (offset 168) 置 0
        struct.pack_into('<Q', original_header_bytes, 168, 0)

        # 现在写入新文件
        with open(output_filename, 'wb') as f_out:
            # 写入更新后的 Header 区（212字节）
            f_out.write(original_header_bytes)
            # 写入原文件中 Header 后到 sampleOffset 部分（状态包等），不修改
            f_out.write(middle_bytes)
            # 写入截取的样本数据部分
            f_out.write(sample_data)
        # print(f"提取完成：共提取 {n_samples_extracted} 帧样本，新文件 {output_filename} 生成。")

    def try_save_as_utc_timezone(self, filepath: Union[str, os.PathLike], force_apply_timezone_offset=False):
        """将PT5的时区修正为UTC时间并保存"""
        if not self.header.timezoneFlag and not force_apply_timezone_offset:
            return False
        with open(self.filename, 'rb') as f:
            mini_bytes = bytearray(f.read(36))
            original_left_bytes = f.read()
        original_ticks = struct.unpack_from('<q', mini_bytes, 28)[0] & 0x7FFFFFFFFFFFFFFF
        delta = self.timezone_delta
        delta_ticks = int(delta.total_seconds() * 1e7)
        new_ticks = (original_ticks + delta_ticks) & 0x7FFFFFFFFFFFFFFF
        struct.pack_into('<q', mini_bytes, 28, new_ticks)
        with open(filepath, 'wb') as f_out:
            f_out.write(mini_bytes)
            f_out.write(original_left_bytes)
        return True

    def get_interval_averages_fast(self,
                                   start_time: Union[datetime, float],
                                   end_time: Union[datetime, float],
                                   interval_seconds: float
                                   ) -> List[Tuple[datetime, datetime, float, float]]:
        """
        一次性批量计算按 interval_seconds 拆分的所有区间平均值
        返回 [(区间开始datetime, 区间结束datetime, avg_current_mA, avg_voltage_V), ...]
        """
        fs = self.header.hardwareRate
        ss = self.header.sampleSize
        offset0 = self.header.sampleOffset
        ts = self.time_scale

        # 1. 计算 start_idx, end_idx（样本索引）
        if isinstance(start_time, datetime):
            start_idx, _ = self.time_index_range(start_time, start_time)
        else:
            start_idx = int(start_time * fs * ts)
        if isinstance(end_time, datetime):
            _, end_idx = self.time_index_range(end_time, end_time)
        else:
            end_idx = int(end_time * fs * ts)

        # 保证边界合法
        start_idx = max(0, min(start_idx, self.header.totalCount))
        end_idx = max(0, min(end_idx, self.header.totalCount))

        # 2. 计算每段样本数及段数
        samples_per_interval = int(interval_seconds * fs * ts)
        n_intervals = (end_idx - start_idx) // samples_per_interval

        if n_intervals <= 0:
            return []

        # 3. 构造所有任务
        tasks = []
        for i in range(n_intervals):
            idx = start_idx + i * samples_per_interval
            byte_off = offset0 + idx * ss
            tasks.append((self.filename, byte_off, samples_per_interval, False))

        # 4. 批量执行
        pool = multiprocessing.dummy.Pool()
        results = pool.map(_process_chunk, tasks)
        pool.close()
        pool.join()

        # 5. 组织返回
        out = []
        base_time = self.header.captureDate
        for i, (sum_i, sum_v, cnt, _) in enumerate(results):
            # 计算时间区间
            seg_start_idx = start_idx + i * samples_per_interval
            seg_end_idx = seg_start_idx + samples_per_interval
            t0 = base_time + timedelta(seconds=seg_start_idx / (fs * ts))
            t1 = base_time + timedelta(seconds=seg_end_idx / (fs * ts))
            # 计算平均值
            avg_i = (sum_i / cnt) / 1000.0 if cnt else None
            avg_v = (sum_v / cnt) * 500e-6 if cnt else None
            out.append((t0, t1, avg_i, avg_v))

        return out


# 示例使用：
if __name__ == '__main__':
    # 请替换为实际的 PT5 文件路径和时区偏移
    _filename = r'D:\pt5_lib\KL8DOU3.0电流图.pt5'
    pt5 = PT5Reader(_filename, datetime.now().astimezone().utcoffset())
    print(f"捕获开始时间：{pt5.header.captureDate}")
    print(f"捕获结束时间：{pt5.header.captureEndDate}")
    print(f"捕获时长：{timedelta(seconds=pt5.header.duration)}")
    print("Header 信息:")
    print(pt5.header)
    print(pt5.get_interval_averages_fast(pt5.header.captureDate, pt5.header.captureEndDate, 1))
    from powertrde.utils.trde import adb
    adb.measure_device_time_offset_ms(adb.first_device())  # 手机时间减去电脑时间
    # 示例：提取指定时间段，生成一个小的 pt5 文件
    # start_dt = datetime.fromisoformat('2025-04-12T03:08:21.239936')
    # end_dt = datetime.fromisoformat('2025-04-12T03:10:22.475187')
    # start_dt = datetime.fromisoformat('2025-04-11T21:02:43.876340')
    # end_dt = datetime.fromisoformat('2025-04-11T21:04:45.099090')
    # output_file = r'D:\pt5_lib\total_power_s.pt5'
    # pt5.extract_time_slice(start_dt, end_dt, output_file)
