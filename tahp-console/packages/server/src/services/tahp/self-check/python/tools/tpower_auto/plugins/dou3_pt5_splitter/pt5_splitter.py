import glob
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Union

from openpyxl.reader.excel import load_workbook

from powertrde.utils import misc_utils, excel_utils, yaml_utils
from pypowertool.pt5reader import PT5Reader


class TimestampPeriodGroup:
    def __init__(self):
        super().__init__()
        self.period_group = []
        self.step_group = []

    def append_period(self, period_name: str, period_desc: str, start_timestamp: float, end_timestamp: float):
        self.period_group.append((period_name, period_desc, start_timestamp, end_timestamp))

    def nature_append(self, period_name: str, period_desc: str, duration: float):
        if not self.period_group:
            start_timestamp = 0
        else:
            start_timestamp = self.period_group[-1][3]
        end_timestamp = start_timestamp + duration
        self.append_period(period_name, period_desc, start_timestamp, end_timestamp)

    def step_detail_append(self, step_detail:str):
        try:
            if not self.period_group[len(self.step_group)]:
                raise Exception('Need a according period_group')
            else:
                self.step_group.append(step_detail)
        except:
            raise Exception('Need a according period_group')

    @staticmethod
    def parse(excel_file: str, name_index=1, desc_index=2, duration_in_minutes_index=4, step_detail_index=7) -> 'TimestampPeriodGroup':
        # 打开工作簿
        workbook = load_workbook(excel_file)
        # 默认读取第一个工作表
        sheet = workbook.worksheets[0]

        g = TimestampPeriodGroup()

        max_row = sheet.max_row
        for i in range(2, max_row + 1):
            name_cell = sheet.cell(row=i, column=name_index)
            if not name_cell.value:
                break
            desc_cell = sheet.cell(row=i, column=desc_index)
            duration_cell = sheet.cell(row=i, column=duration_in_minutes_index)
            g.nature_append(str(name_cell.value), str(desc_cell.value), float(duration_cell.value) * 60.0)
            try:
                step_detail = sheet.cell(row=i, column=step_detail_index)
                g.step_detail_append(str(step_detail.value))
            except:
                pass
        return g


@dataclass
class _PT5SummaryGroup:
    avg_cur_summary = 0.0
    avg_vol_summary = 0.0
    duration_summary = 0.0

    def add_computing_unit(self, avg_cur: float, avg_vol: float, duration: float):
        self.avg_cur_summary += avg_cur * duration
        self.avg_vol_summary += avg_vol * duration
        self.duration_summary += duration

    def cal_avg_cur(self):
        if self.duration_summary <= 0:
            return 0.0
        return self.avg_cur_summary / self.duration_summary

    def cal_avg_vol(self):
        if self.duration_summary <= 0:
            return 0.0
        return self.avg_vol_summary / self.duration_summary

def update_pt5_summary_group_dict(pt5_summary_group_dict: dict, unit_report_unit_dict: dict):
    unit_start_time = datetime.fromisoformat(unit_report_unit_dict['start_time'])
    unit_end_time = datetime.fromisoformat(unit_report_unit_dict['end_time'])
    avg_cur = unit_report_unit_dict['data']['avg_cur']
    avg_vol = unit_report_unit_dict['data']['avg_vol']
    screen_state = unit_report_unit_dict.get('screen_state')
    if not screen_state:
        if '灭屏' in unit_report_unit_dict.get('case_desc', ''):
            screen_state = 'off'
        else:
            screen_state = 'on'
    test_duration = (unit_end_time - unit_start_time).total_seconds()
    pt5_summary_group_dict.setdefault(screen_state, _PT5SummaryGroup()).add_computing_unit(avg_cur, avg_vol,
                                                                                          test_duration)
    pt5_summary_group_dict.setdefault('total', _PT5SummaryGroup()).add_computing_unit(avg_cur, avg_vol,
                                                                                     test_duration)


class Dou3Pt5Splitter:
    def __init__(self, meta_report, timezone_delta: timedelta,
                 period_group: TimestampPeriodGroup, pt5_path):
        super().__init__()
        self.meta_report = meta_report
        self.timezone_delta = timezone_delta
        self.period_group = period_group
        self.pt5_path = pt5_path

    def _cal_pt5_report(self, matching_file_names):
        pt5_file = os.path.join(self.meta_report, 'total_power_new.pt5') # 转换过时区
        if not os.path.exists(pt5_file):
            pt5_file = self.pt5_path
            if not os.path.exists(pt5_file):
                return None

        pt5_summary_group_dict = {}
        screen_on_and_off_dict = []
        gap_time_to_pc = 0.0
        screen_off_avg_current = 0.0
        screen_on_avg_current = 0.0
        total_avg_current = 0.0
        start_time = None
        end_time = None

        timezone_delta = datetime.now().astimezone().utcoffset()

        process_file = os.path.join(self.meta_report, 'session_process_report.yaml')
        if os.path.exists(process_file):
            start_time = yaml_utils.read_yaml(process_file).get('start_time', None)
            end_time = yaml_utils.read_yaml(process_file).get('last_update_time', None)

        filter_matching_files = []
        for file_name in matching_file_names:
            unit_file = os.path.join(self.meta_report, file_name)
            unit_report_dict = yaml_utils.read_yaml(unit_file)
            pt5_slice_file = os.path.join(self.meta_report, file_name[:-5] + '.pt5')
            if unit_report_dict:
                avg_cur = unit_report_dict['data']['avg_cur']
                if avg_cur and os.path.exists(pt5_slice_file):
                    update_pt5_summary_group_dict(pt5_summary_group_dict, unit_report_dict)
                else:
                    filter_matching_files.append((unit_file, unit_report_dict))
        pt5reader = PT5Reader(pt5_file, timezone_delta=timezone_delta)
        if filter_matching_files:
            # print('Start deal time: ' + str(datetime.now()))
            for to_deal_file in filter_matching_files:
                unit_start_time = datetime.fromisoformat(to_deal_file[1]['start_time'])
                unit_end_time = datetime.fromisoformat(to_deal_file[1]['end_time'])
                pt5_slice_file = os.path.join(os.path.dirname(to_deal_file[0]),
                                              os.path.basename(to_deal_file[0])[:-5] + '.pt5')
                pt5reader.extract_time_slice(unit_start_time, unit_end_time, pt5_slice_file, auto_correction_time=True)
                c, v = pt5reader.get_average_current_voltage(unit_start_time, unit_end_time, auto_correction_time=True)
                # 确保 'data' 键存在
                to_deal_file[1]['data']['avg_cur'] = c
                to_deal_file[1]['data']['avg_vol'] = v
                yaml_utils.write_yaml(to_deal_file[1], to_deal_file[0])
                update_pt5_summary_group_dict(pt5_summary_group_dict, to_deal_file[1])

        try:
            # 单独生成亮灭屏的数据
            from bugreport_utils.bugreport_parser import BugreportParser
            from pathlib import Path
            bugreport_file = str(list(Path(self.meta_report).glob("bugreport*.txt"))[0].absolute())
            parser = BugreportParser(bugreport_file, gap_time_to_pc)
            all_data = parser.analyze_screen_intervals(datetime.fromisoformat(start_time),
                                                       datetime.fromisoformat(end_time))
            total_off_time = all_data['total_off']
            total_on_time = all_data['total_on']
            total_time = all_data['total']
            screen_on_current = 0.0
            screen_off_current = 0.0
            for i, (start, end, screen_status) in enumerate(all_data['final_intervals']):
                c, v = pt5reader.get_average_current_voltage(start, end, auto_correction_time=True)
                screen_on_and_off_dict.append([start, end, screen_status, c, v])
                if screen_status == 'on':
                    screen_on_current += c * ((end - start).total_seconds())
                elif screen_status == 'off':
                    screen_off_current += c * ((end - start).total_seconds())

            screen_off_avg_current = screen_off_current / total_off_time.total_seconds()
            screen_on_avg_current = screen_on_current / total_on_time.total_seconds()
            total_avg_current = (screen_on_current + screen_off_current) / total_time.total_seconds()
        except Exception as _e:
            pass

        return pt5_summary_group_dict, screen_on_and_off_dict, [screen_off_avg_current, screen_on_avg_current,
                                                                total_avg_current]

    def check_and_find_bugreport(self):
        import re
        import zipfile

        base_path = Path(self.meta_report)
        if list(base_path.glob("*bugreport*.txt")):
            return True
        try:
            bugreport_zip_paths = glob.glob(os.path.join(self.meta_report, "bugreport*.zip"))
            if not bugreport_zip_paths:
                    print(f"bureport文件不存在")
                    return False
            bugreport_zip_path = bugreport_zip_paths[0]

            with zipfile.ZipFile(bugreport_zip_path, 'r') as zf:
                matched_txts = [f for f in zf.namelist() if re.search(r"bugreport.*\.txt", f)]
                with zf.open(matched_txts[0], "r") as src_file:
                    with open(os.path.join(self.meta_report, 'bugreport.txt'), 'wb') as wf:
                        for chunk in iter(lambda: src_file.read(1024 * 1024), b''):
                            wf.write(chunk)
            return True
        except:
            return False

    def gen_data_report(self):
        matching_files = []

        # 使用 glob 模块查找文件夹中所有符合条件的 yaml 文件
        search_pattern = os.path.join(self.meta_report, '*dou3*.yaml')
        for file_path in glob.glob(search_pattern):
            matching_files.append(file_path)
        matching_files.sort(key=lambda x: os.path.basename(x))  # 排序从小到大，便于后期的时间统计
        if self.check_and_find_bugreport():
             pt5_summary_group_dict,  screen_on_and_off_dict, screen_on_and_off_avg_dict = self._cal_pt5_report(matching_files)
        else:
            raise FileNotFoundError("Did not find bugreport")

        start_time = None
        end_time = None
        pass_num = 0
        fail_num = 0

        if len(matching_files) < 1:
            return False

        res_data = [(['id', 25], ['name', 25], ['desc', 45], ['result', 10], ['starttime', 33], ['endtime', 33],
                     ['duration', 18], ['expect_duration', 18], ['duration_sec', 18], ['avg_cur', 10], ['avg_vol', 10], ['avg_cur_4v', 10])]

        for index, f in enumerate(matching_files):
            _data = {}
            meta_data = yaml_utils.read_yaml_retain_annotations(f)
            if index == 0:
                start_time = meta_data['start_time']
            if index == len(matching_files) - 1:
                end_time = meta_data['end_time']

            _data['id'] = str(index)
            _data['name'] = os.path.basename(f)[:-5]
            _data['desc'] = meta_data['case_desc'].strip()
            _data['result'] = meta_data['test_result']
            if meta_data['test_result'] == 'pass':
                pass_num = pass_num + 1
            else:
                fail_num = fail_num + 1

            _case_start_time = datetime.fromisoformat(meta_data['start_time'])
            _case_end_time = datetime.fromisoformat(meta_data['end_time'])

            _data['starttime'] = str(_case_start_time)
            _data['endtime'] = str(_case_end_time)
            _data['duration'] = str(self.calculate_time_difference(meta_data['start_time'], meta_data['end_time']))
            _data['expect_duration'] = self.calculate_time_difference_sec(meta_data['expect_duration'])
            _data['duration_sec'] = str((_case_end_time - _case_start_time).total_seconds())
            _data['avg_cur'] = meta_data['data']['avg_cur']
            _data['avg_vol'] = meta_data['data']['avg_vol']
            _data['avg_cur_4v'] = _data['avg_cur'] * _data['avg_vol'] / 4.0

            res_data.append(_data)

        # 开始统计总用例情况
        formatted_time = self.calculate_time_difference(start_time, end_time)

        res_data_home = [(['start_time', 40], ['end_time', 40], ['duration', 40], ['pass_num', 18], ['fail_num', 18],
                          ['pass_percent', 18], ['overall_cur', 18], ['screen_on_cur', 18], ['screen_off_cur', 18],
                          ['overall_cur_4v', 18], ['screen_on_cur_4v', 18], ['screen_off_cur_4v', 18])]

        total_excel_unit = {
            'start_time': str(datetime.fromisoformat(start_time)),
            'end_time': str(datetime.fromisoformat(end_time)),
            'duration': str(formatted_time),
            'pass_num': str(pass_num),
            'fail_num': str(fail_num),
            'pass_percent': f'{(pass_num * 100 / (fail_num + pass_num)):.2f}%'
        }

        try:
            total_excel_unit['overall_cur'] = screen_on_and_off_avg_dict[2]
        except Exception:
            total_excel_unit['overall_cur'] = 0.0

        try:
            total_excel_unit['screen_on_cur'] = screen_on_and_off_avg_dict[1]
        except Exception:
            total_excel_unit['screen_on_cur'] = 0.0

        try:
            total_excel_unit['screen_off_cur'] = screen_on_and_off_avg_dict[0]
        except Exception:
            total_excel_unit['screen_off_cur'] = 0.0

        try:
            total_excel_unit['overall_cur_4v'] = total_excel_unit['overall_cur'] * pt5_summary_group_dict[
                'total'].cal_avg_vol() / 4.0
        except Exception:
            total_excel_unit['overall_cur_4v'] = 0.0

        try:
            total_excel_unit['screen_on_cur_4v'] = total_excel_unit['screen_on_cur'] * pt5_summary_group_dict[
                'on'].cal_avg_vol() / 4.0
        except Exception:
            total_excel_unit['screen_on_cur_4v'] = 0.0

        try:
            total_excel_unit['screen_off_cur_4v'] = total_excel_unit['screen_off_cur'] * pt5_summary_group_dict[
                'off'].cal_avg_vol() / 4.0
        except Exception:
            total_excel_unit['screen_off_cur_4v'] = 0.0

        res_data_home.append(total_excel_unit)

        # 单独生成亮灭屏区间电流
        res_data_cur = [(['id', 10], ['starttime', 33], ['endtime', 33], ['duration_sec', 18], ['screen', 10],
                         ['avg_cur', 25], ['avg_vol', 10], ['avg_cur_4v', 10])]

        for index, (start, end, screen_status, c, v) in enumerate(screen_on_and_off_dict):
            _data = {}
            _data['id'] = str(index)
            _data['starttime'] = str(start)
            _data['endtime'] = str(end)
            _data['duration_sec'] = str((end - start).total_seconds())
            _data['screen'] = screen_status
            _data['avg_cur'] = c
            _data['avg_vol'] = v
            _data['avg_cur_4v'] = _data['avg_cur'] * _data['avg_vol'] / 4.0

            res_data_cur.append(_data)

        save_path = os.path.join(self.meta_report, "testReport.xlsx")
        excel_utils.gen_excel_util(res_data_home, save_path, 'total')
        excel_utils.gen_excel_util(res_data, save_path, 'report')
        excel_utils.gen_excel_util(res_data_cur, save_path, 'current')

        return save_path, float(pass_num / (fail_num + pass_num))

    def calculate_time_difference(self, start_time_str, end_time_str):
        # 解析ISO格式的时间字符串为datetime对象
        start_time = datetime.fromisoformat(start_time_str)
        end_time = datetime.fromisoformat(end_time_str)

        # 计算时间差
        time_difference = end_time - start_time

        # 获取总秒数
        total_seconds = time_difference.total_seconds()

        # 计算小时、分钟和秒
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        seconds = int(total_seconds % 60)

        # 格式化为“00::20:15”的字符串
        formatted_time = f"{hours:02}:{minutes:02}:{seconds:02}"

        return formatted_time


    def calculate_time_difference_sec(self, total_seconds):
        # 计算小时、分钟和秒
        total_seconds = int(total_seconds)
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        seconds = int(total_seconds % 60)

        # 格式化为“00:20:15”的字符串
        formatted_time = f"{hours:02}:{minutes:02}:{seconds:02}"

        return str(formatted_time)



if __name__ == '__main__':
    TimestampPeriodGroup.parse(r'C:\Users\chengpeng.zheng\Downloads\3.0动态续航模型用例数据及自动化.xlsx')
