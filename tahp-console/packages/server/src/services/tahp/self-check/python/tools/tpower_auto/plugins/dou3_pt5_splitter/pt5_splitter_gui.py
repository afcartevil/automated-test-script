import os
import sys
import yaml
from datetime import datetime, timedelta
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QFileDialog, QComboBox,
    QTabWidget, QGroupBox
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QShortcut, QKeySequence
from dou3_pt5_splitter.pt5_splitter import TimestampPeriodGroup, Dou3Pt5Splitter
from powertrde.utils.window_utils import UnclosableWindow, show_warning_box, show_message_box
from pypowertool.pt5reader import PT5Reader

VERSION = '1.3'

class GeneratorUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f'dou3 数据辅助生成与报告 v{VERSION}')
        self.resize(900, 700)
        # 默认用例文件夹为当前工作目录下的 'cases'
        # self.case_folder = os.path.join(os.getcwd(), 'cases')
        # 修改case_folder的获取方式，适应打包环境
        self.case_folder = self.get_cases_path()
        self.executor = None
        self.initUI()

    def initUI(self):
        self.tabs = QTabWidget(self)
        self.tabs.addTab(self.create_support_tab(), '辅助测试')
        self.tabs.addTab(self.create_report_tab(), '输出报告')

        main_layout = QVBoxLayout(self)
        main_layout.addWidget(self.tabs)
        self.setLayout(main_layout)

    def get_cases_path(self):
        """获取cases文件夹路径，适用于开发和打包环境"""
        try:
            # PyInstaller打包后的临时目录
            base_path = sys._MEIPASS
        except AttributeError:
            # 开发环境，使用当前工作目录
            base_path = os.getcwd()

        return os.path.join(base_path, 'cases')
    def create_support_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(10)

        # 用例选择
        case_box = QGroupBox('用例配置')
        cl = QHBoxLayout(case_box)
        cl.addWidget(QLabel('选择用例表:'))
        self.case_combo = QComboBox()
        cl.addWidget(self.case_combo)
        layout.addWidget(case_box, 1)

        self.load_case_files()

        # 执行区：直接嵌入 CaseExecutorWindow
        exec_area = QGroupBox('执行工具')
        self.exec_layout = QVBoxLayout(exec_area)
        # Button to initialize executor if not yet
        self.open_exec_btn = QPushButton('打开 dou3 辅助执行工具')
        self.open_exec_btn.clicked.connect(self.init_executor)

        self.exec_layout.addWidget(self.open_exec_btn)
        layout.addWidget(exec_area, 9)

        return page

    def create_report_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(10)

        # meta_report
        mr = QGroupBox('Meta Report 文件(使用辅助工具测试时生成的文件夹, 该文件夹下需要有bugreport文件)')
        ml = QHBoxLayout(mr)
        ml.addWidget(QLabel('路径:'))
        self.meta_path = QLineEdit()
        ml.addWidget(self.meta_path)
        btn_m = QPushButton('Select...')
        btn_m.clicked.connect(lambda: self.select_file(self.meta_path, '', 'folder'))
        ml.addWidget(btn_m)
        layout.addWidget(mr)

        # bugreport
        br = QGroupBox('PT5 (.pt5)文件')
        bl = QHBoxLayout(br)
        bl.addWidget(QLabel('路径:'))
        self.pt5_path = QLineEdit()
        bl.addWidget(self.pt5_path)
        btn_b = QPushButton('Select...')
        btn_b.clicked.connect(lambda: self.select_file(self.pt5_path, 'Text Files (*.pt5)'))
        bl.addWidget(btn_b)
        layout.addWidget(br)

        # 时区
        tzb = QGroupBox('PT5 文件时区')
        tzl = QHBoxLayout(tzb)
        tzl.addWidget(QLabel('Offset (小时):'))
        self.tz_input = QLineEdit(f"{self.get_system_timezone():.1f}")
        tzl.addWidget(self.tz_input)
        layout.addWidget(tzb)

        # 按钮
        btn_layout = QHBoxLayout()
        btn_gen = QPushButton('开始生成数据')
        btn_save = QPushButton('另存为 UTC 时区')
        btn_layout.addWidget(btn_gen)
        btn_layout.addWidget(btn_save)
        layout.addLayout(btn_layout)

        btn_gen.clicked.connect(self.on_start_clicked)
        btn_save.clicked.connect(self.on_save_utc_clicked)
        return page

    def load_case_files(self):
        self.case_combo.clear()
        if not os.path.isdir(self.case_folder):
            self.case_combo.addItem('未找到用例文件夹')
            return
        files = sorted(f for f in os.listdir(self.case_folder) if f.endswith(('.xls','.xlsx')))
        if not files:
            self.case_combo.addItem('无 Excel 文件')
        else:
            self.case_combo.addItems(files)

    def get_selected_case_path(self):
        f = self.case_combo.currentText()
        return None if f.startswith(('未','无')) else os.path.join(self.case_folder, f)

    def select_file(self, field, filt='', path_type='file'):
        """通用路径选择接口"""
        if path_type == 'folder':
            p = QFileDialog.getExistingDirectory(self, 'Select Folder', '')
        else:
            p, _ = QFileDialog.getOpenFileName(self, 'Select File', '', filt)
        if p:
            field.setText(p)

    def get_system_timezone(self):
        off = datetime.now().astimezone().utcoffset()
        return off.total_seconds()/3600 if off else 0

    def on_start_clicked(self):
        excel = self.get_selected_case_path()
        meta = self.meta_path.text()
        pt5_path = self.pt5_path.text()
        tz = float(self.tz_input.text())
        with (UnclosableWindow('Generating', '请稍候...')):
            g = TimestampPeriodGroup.parse(excel)
            dou3_pt5_splitter = Dou3Pt5Splitter(meta, timedelta(hours=tz), g, pt5_path)
            dou3_pt5_splitter.gen_data_report()
        show_message_box('Success', '数据生成完成')

    def on_save_utc_clicked(self):
        meta = self.meta_path.text()
        tz = float(self.tz_input.text())
        pt5 = os.path.join(meta, 'total_power.pt5')
        out = os.path.join(meta, 'total_power_new.pt5')
        reader = PT5Reader(pt5, timedelta(hours=tz))
        with UnclosableWindow('Saving UTC','请稍候...'):
            reader.try_save_as_utc_timezone(out)
        show_message_box('Success', f'UTC 文件已保存到 {out}')

    def init_executor(self):
        excel = self.get_selected_case_path()
        if not excel:
            show_warning_box('Error', '请先确认 cases 文件夹下有有效用例表')
            return
        if self.executor:
            self.exec_layout.removeWidget(self.executor)
            self.executor.deleteLater()
        g = TimestampPeriodGroup.parse(excel)
        self.executor = CaseExecutorWindow(g)
        self.exec_layout.addWidget(self.executor)
        self.open_exec_btn.setEnabled(False)

class CaseExecutorWindow(QWidget):
    def __init__(self, excel_data: TimestampPeriodGroup):
        super().__init__()
        self.case_data = excel_data.period_group
        self.case_detail = excel_data.step_group
        self.result = []
        self.current_case_index = -1
        self.start_time = None
        self.case_start_time = None
        self.session_start_time = None  # 整个会话开始时间
        self.pass_count = 0
        self.fail_count = 0

        # self.overtime_carry = 0  # 当前用例是否因上一条超时而扣时 是否需要加这个功能，一般手工测试只要时间切得准是否不需要额外的时间校准

        # 创建结果目录
        self.result_dir = f"test_dou3_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        os.makedirs(self.result_dir, exist_ok=True)

        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()

        self.case_info_label = QLabel("用例ID")
        self.time_info_label = QLabel("测试总耗时: 00:00:00 | 当前剩余时间: 00:00")
        self.tip_label = QLabel("提示：按回车开始测试")
        self.case_next_info_label = QLabel("下一条用例ID")

        self.start_btn = QPushButton("点击进入执行模式")
        self.start_btn.clicked.connect(self.on_exec_start)

        layout.addWidget(self.case_info_label)
        layout.addWidget(self.time_info_label)
        layout.addWidget(self.case_next_info_label)
        layout.addWidget(self.tip_label)
        layout.addWidget(self.start_btn)

        self.setLayout(layout)
        self.setWindowTitle("用例执行助手")
        self.resize(600, 300)

        # 回车快捷键
        from PyQt6.QtGui import QShortcut, QKeySequence
        self.enter_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Return), self)
        self.enter_shortcut.activated.connect(self.on_enter_pressed)

        # F键失败
        self.fail_shortcut = QShortcut(QKeySequence(Qt.Key.Key_F), self)
        self.fail_shortcut.activated.connect(self.mark_result_fail)

        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.update_time_display)

    def on_exec_start(self):
        self.current_case_index = -1
        self.tip_label.setText("按回车开始第一条用例")
        self.start_btn.setEnabled(False)

    def on_enter_pressed(self):
        now = datetime.now()

        if not self.case_data:
            return

        self.tip_label.setText(
            "测试中... 按回车键通过并进入下一个，失败则重新打开该应用并停留到该用例的时间结束，并F键标记失败"
        )

        if self.current_case_index == -1:
            self.case_start_time = now
            self.start_time = now
            self.session_start_time = self.case_start_time
            self.current_case_index = 0
            self.update_timer.start(1000)
            self.display_current_case()
            return

        # 当前用例已开始，检查是否允许进入下一条（剩余5s内或超时）
        case_duration = int(self.case_data[self.current_case_index][3] - self.case_data[self.current_case_index][2])
        elapsed_seconds = (now - self.case_start_time).total_seconds()
        remaining_seconds = case_duration - elapsed_seconds

        if remaining_seconds > 5:
            self.tip_label.setText(
                f'<font color="red">还剩 {int(remaining_seconds)} 秒，不允许跳转下一条。</font>'
            )
            return

        # 可以正常记录并跳转
        self.record_case_result(now, "pass")

    def mark_result_fail(self):
        """F键标记失败"""
        now = datetime.now()

        if self.current_case_index == -1:
            return

        self.record_case_result(now, "fail")

    def record_case_result(self, end_time, test_result):
        """记录用例结果的通用方法"""
        case = self.case_data[self.current_case_index]

        if test_result == 'pass':
            self.pass_count += 1
        elif test_result == 'fail':
            self.fail_count += 1

        # 计算实际耗时和预期耗时
        actual_duration = end_time - self.case_start_time
        expect_duration = int(case[3] - case[2])

        # 生成时间戳
        timestamp = end_time.strftime('%Y%m%d%H%M%S%f')[:-3]  # 精确到毫秒

        case_result = {
            "case_id": case[0],
            "case_desc": case[1],
            "start_time": self.case_start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "data":{
                "avg_cur": 0,
                "avg_vol": 0
            },
            "expect_duration": expect_duration,
            "duration": str(actual_duration),
            "test_result": test_result
        }

        # 保存单个用例结果文件
        filename = f"{timestamp}_{test_result}_dou3_{case[0].replace(' ', '_').replace('+', '_').replace('-', '_')}.yaml"
        filepath = os.path.join(self.result_dir, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            yaml.dump(case_result, f, allow_unicode=True, default_flow_style=False)

        self.current_case_index += 1

        if self.current_case_index >= len(self.case_data):
            self.tip_label.setText("全部用例测试完成")
            self.update_timer.stop()
            self.save_session_report(end_time)
            return

        self.case_start_time = datetime.now()
        self.display_current_case()

    def update_time_display(self):
        if (self.start_time is None or
                self.current_case_index == -1 or
                self.current_case_index >= len(self.case_data) or
                not self.case_data):
            return

        now = datetime.now()
        total_elapsed = now - self.start_time
        # 获取当前用例的持续时间（秒）
        case_duration = int(self.case_data[self.current_case_index][3] - self.case_data[self.current_case_index][2])

        # 计算当前用例已经运行的时间
        case_elapsed = now - self.case_start_time

        # 计算剩余时间
        remaining_seconds = int(case_duration - case_elapsed.total_seconds())
        # 因为 14:42.33s会显示14.42s, 所以精进1位
        case_elapsed_str = str(case_elapsed + timedelta(seconds=1)).split('.')[0]
        total_elapsed_str = str(total_elapsed + timedelta(seconds=1)).split('.')[0]

        if remaining_seconds <= 0:
            overtime_str = str(timedelta(seconds=abs(remaining_seconds))).split('.')[0]
            self.time_info_label.setText(
                f'<font size="5" color="red"><b>测试总耗时: {total_elapsed_str}<br>'
                f'当前用例耗时: {case_elapsed_str} | <u>已超时: {overtime_str}</u></b></font>'
            )
            self.tip_label.setText('<font size="4" color="red"><b>当前用例已超时，请按回车切换</b></font>')

        else:
            remaining_str = str(timedelta(seconds=remaining_seconds)).split('.')[0]

            # 动态样式颜色等级
            if remaining_seconds <= 10:
                font_size = 6
                color = "red"
            elif remaining_seconds <= 30:
                font_size = 5
                color = "red"
            elif remaining_seconds <= 60:
                font_size = 4
                color = "orange"
            else:
                font_size = 3
                color = "black"

            self.time_info_label.setText(
                f'<font size="{font_size}" color="{color}"><b>测试总耗时: {total_elapsed_str}<br>'
                f'当前用例耗时: {case_elapsed_str} | 剩余时间: {remaining_str}</b></font>'
            )

    def display_current_case(self):
        c = self.case_data[self.current_case_index]
        if self.current_case_index+1 < len(self.case_data):
            next_c = self.case_data[self.current_case_index+1]
        else:
            next_c = "end"
        # 获取当前时间
        current_time = datetime.now()
        duration_seconds = int(c[3]) - int(c[2])
        # 计算结束时间
        end_time = current_time + timedelta(seconds=duration_seconds)

        # 格式化时间显示
        start_time_str = current_time.strftime("%H:%M:%S")
        end_time_str = end_time.strftime("%H:%M:%S")

        self.case_info_label.setWordWrap(True)
        self.case_info_label.setStyleSheet("font-size: 14px;")
        html_content = f"""
        {c[0]}<br>
        第 {self.current_case_index + 1} 条:<br>
        <span style="color: HotPink; font-weight: bold; font-size: 16px;">用例描述:</span> {c[1]}<br><br>
        <span style="color: HotPink; font-weight: bold; font-size: 16px;">步骤:</span> {self.case_detail[self.current_case_index]}<br><br>
        <span style="color: HotPink; font-weight: bold; font-size: 16px;">预期时长:</span> {start_time_str} —— {end_time_str}
        """

        self.case_info_label.setText(html_content)

        self.case_next_info_label.setWordWrap(True)
        self.case_next_info_label.setStyleSheet("font-size: 13px; color: DarkGray;")
        if next_c == "end":
            self.case_next_info_label.setText(
                f"这是最后一条用例！"
            )
        else:
            self.case_next_info_label.setText(
                f"下一条用例{next_c[0]}\n第 {self.current_case_index + 2} 条:\n用例描述: {next_c[1]}\n"
                f"步骤: {self.case_detail[self.current_case_index+1]}\n"
            )

    def save_session_report(self, end_time):
        total_duration = (end_time - self.session_start_time).total_seconds()
        total_count = len(self.case_data)

        # 计算通过率和失败率
        pass_rate = self.pass_count / total_count if total_count > 0 else 0
        fail_rate = self.fail_count / total_count if total_count > 0 else 0

        session_report = {
            "duration": total_duration,
            "fail_count": self.fail_count,
            "fail_rate": fail_rate,
            "finish_count": total_count,
            "last_update_time": end_time.isoformat(),
            "pass_count": self.pass_count,
            "pass_rate": pass_rate,
            "start_time": self.session_start_time.isoformat(),
            "timezone_delta": datetime.now().astimezone().utcoffset().total_seconds(),
            "total_count": total_count
        }

        save_path = os.path.join(self.result_dir, "session_process_report.yaml")
        with open(save_path, "w", encoding="utf-8") as f:
            yaml.dump(session_report, f, allow_unicode=True)
        self.tip_label.setText(f"测试完成！结果保存在 {self.result_dir}")


if __name__ == '__main__':
    app = QApplication(sys.argv)
    win = GeneratorUI()
    win.show()
    sys.exit(app.exec())
