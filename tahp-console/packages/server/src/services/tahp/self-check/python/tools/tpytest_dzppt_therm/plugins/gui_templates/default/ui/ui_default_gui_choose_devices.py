import sys
from typing import List
from PyQt6 import QtCore, QtGui, QtWidgets
from gui_templates.default.vm.default_gui_main_vm import DefaultGuiMainVM
from powertrde.utils.trde import adb
from powertrde.framework.i18n import I18n


class DefaultDeviceSelectionWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.start_gui_entry_py = None
        self.setWindowTitle(I18n.gen_str("Device Selection","设备选择"))
        self.setFixedSize(500, 400)

        # 创建 ViewModel 实例
        self.vm = DefaultGuiMainVM()

        self.central_widget = QtWidgets.QWidget()
        self.setCentralWidget(self.central_widget)

        self.layout = QtWidgets.QVBoxLayout(self.central_widget)

        # 标题
        self.title_label = QtWidgets.QLabel(I18n.gen_str("Select the device to be tested","选择要测试的设备"))
        self.title_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        font = QtGui.QFont()
        font.setPointSize(14)
        font.setBold(True)
        self.title_label.setFont(font)
        self.layout.addWidget(self.title_label)

        # 设备表格（替代原来的列表和表格）
        self.device_table = QtWidgets.QTableWidget()
        self.device_table.setColumnCount(3)
        self.device_table.setHorizontalHeaderLabels([I18n.gen_str("Select", "选择"),I18n.gen_str("Device ID", "设备ID"),I18n.gen_str("Type", "类型")])
        self.device_table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        self.layout.addWidget(self.device_table)

        # 按钮布局
        self.button_layout = QtWidgets.QHBoxLayout()

        # 新增全选/全不选按钮
        self.select_all_button = QtWidgets.QPushButton(I18n.gen_str("Select All", "全选"))
        self.select_all_button.clicked.connect(self.select_all_devices)
        self.button_layout.addWidget(self.select_all_button)

        self.deselect_all_button = QtWidgets.QPushButton(I18n.gen_str("Deselect All", "全不选"))
        self.deselect_all_button.clicked.connect(self.deselect_all_devices)
        self.button_layout.addWidget(self.deselect_all_button)

        # 刷新按钮
        self.refresh_button = QtWidgets.QPushButton(I18n.gen_str("Refresh Device List", "刷新设备列表"))
        self.refresh_button.clicked.connect(self.refresh_devices)
        self.button_layout.addWidget(self.refresh_button)

        # 开始按钮
        self.start_button = QtWidgets.QPushButton(I18n.gen_str("Start Test", "开始测试"))
        self.start_button.clicked.connect(self.start_test)
        self.button_layout.addWidget(self.start_button)

        self.layout.addLayout(self.button_layout)

        # 状态标签
        self.status_label = QtWidgets.QLabel()
        self.status_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self.status_label)

        # 存储主窗口类
        self.main_window_class = None

        # 初始刷新设备
        self.refresh_devices()

    def set_main_window_class(self, main_window_class):
        """设置要打开的主窗口类"""
        self.main_window_class = main_window_class

    def refresh_devices(self):
        """刷新设备列表，使用实际连接的设备"""
        try:
            # 调用 VM 的刷新方法
            self.vm.refresh_device_list()

            # 清空表格
            self.device_table.setRowCount(0)

            # 获取测试机和辅助机列表
            test_devices = self.vm.device_id_list
            copilot_devices = self.vm.c_device_id_list

            # 添加测试机
            for device_id in test_devices:
                self._add_device_to_table(device_id, I18n.gen_str("Test Device", "测试机"))

            # 添加辅助机
            for device_id in copilot_devices:
                self._add_device_to_table(device_id, I18n.gen_str("Copilot Device", "辅助机"))

            # 调整列宽
            self.device_table.resizeColumnsToContents()

            # 默认全选所有设备
            self.select_all_devices()

            self.status_label.setText(
                I18n.gen_str(
                    f"Found {len(test_devices)} test device(s) and {len(copilot_devices)} copilot device(s)",
                    f"找到 {len(test_devices)} 台测试机和 {len(copilot_devices)} 台辅助机"
                )
            )

        except Exception as e:
            self.status_label.setText(
                I18n.gen_str(
                    f"Failed to refresh devices: {str(e)}",
                    f"刷新设备失败: {str(e)}"
                )
            )
            QtWidgets.QMessageBox.warning(
                self,
                I18n.gen_str("Error", "错误"),
                I18n.gen_str(f"Failed to refresh devices:\n{str(e)}", f"刷新设备失败:\n{str(e)}")
            )

    def select_all_devices(self):
        """选中所有设备"""
        for row in range(self.device_table.rowCount()):
            check_box = self.device_table.cellWidget(row, 0).findChild(QtWidgets.QCheckBox)
            check_box.setChecked(True)

    def deselect_all_devices(self):
        """取消选中所有设备"""
        for row in range(self.device_table.rowCount()):
            check_box = self.device_table.cellWidget(row, 0).findChild(QtWidgets.QCheckBox)
            check_box.setChecked(False)

    def _add_device_to_table(self, device_id, device_type):
        """添加设备到表格"""
        row = self.device_table.rowCount()
        self.device_table.insertRow(row)

        # 选择框
        check_box = QtWidgets.QCheckBox()
        check_box.setChecked(False)
        cell_widget = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(cell_widget)
        layout.addWidget(check_box)
        layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.setContentsMargins(0, 0, 0, 0)
        self.device_table.setCellWidget(row, 0, cell_widget)

        # 设备ID（带型号）
        model = adb.device_model_simple(device_id)
        self.device_table.setItem(row, 1, QtWidgets.QTableWidgetItem(f"{device_id} ({model})"))

        # 设备类型
        self.device_table.setItem(row, 2, QtWidgets.QTableWidgetItem(device_type))

        # 存储原始数据
        self.device_table.item(row, 1).setData(QtCore.Qt.ItemDataRole.UserRole, (device_id, device_type))

    def start_test(self):
        """为每个选中的设备单独执行启动命令"""
        selected_devices = []

        # 收集选中的测试机设备
        for row in range(self.device_table.rowCount()):
            check_box = self.device_table.cellWidget(row, 0).findChild(QtWidgets.QCheckBox)
            if check_box.isChecked():
                device_id, device_type = self.device_table.item(row, 1).data(QtCore.Qt.ItemDataRole.UserRole)
                if device_type == "测试机":
                    selected_devices.append(device_id)

        if not selected_devices:
            QtWidgets.QMessageBox.warning(
                self,
                I18n.gen_str("Warning", "警告"),
                I18n.gen_str("Please select at least one test device", "请至少选择一台测试机")
            )
            return

        # 关闭设备选择窗口
        self.close()

        batch_gui_excutor = DefaultBatchGuiExecutor(device_ids=selected_devices, gui_file_path=self.start_gui_entry_py)
        batch_gui_excutor.start()

class DefaultBatchGuiExecutor:
    def __init__(self, device_ids: List[str], gui_file_path: str):
        self.device_ids = device_ids
        self.gui_file_path = gui_file_path

    def start(self):
        from powertrde.utils import misc_utils
        run_method = misc_utils.run_command_detached
        for d in self.device_ids:
            cmd = [sys.executable, self.gui_file_path, '--start', '--device_id', d]
            run_method(cmd, shell=True)




if __name__ == "__main__":
    import sys

    class MainWindow(QtWidgets.QMainWindow):
        def __init__(self, test_device, copilot_device=None):
            super().__init__()
            from gui_templates.default.ui.ui_default_gui_main_window import Ui_DefaultGuiMainWindow
            self.ui = Ui_DefaultGuiMainWindow()
            self.ui.setupUi(self)
            self.setWindowTitle(f"性能测试 - {test_device}" + (f" (辅助机: {copilot_device})" if copilot_device else ""))


    app = QtWidgets.QApplication(sys.argv)

    # 创建设备选择窗口
    selector = DefaultDeviceSelectionWindow()
    selector.set_main_window_class(MainWindow)
    selector.show()

    sys.exit(app.exec())
