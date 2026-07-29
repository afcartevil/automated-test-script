import sys
from typing import List

from PyQt6.QtWidgets import QApplication

from gui_templates.default.ui.ui_default_gui_choose_devices import DefaultDeviceSelectionWindow


class _DefaultDeviceSelectionWindow(DefaultDeviceSelectionWindow):
    def __init__(self, start_gui_entry_py):
        super().__init__()
        self.start_gui_entry_py = start_gui_entry_py


# 打开选择设备的界面
class DefaultBatchGuiEntry:

    def main(self, start_gui_entry_py):
        app = QApplication(sys.argv)
        selector = _DefaultDeviceSelectionWindow(start_gui_entry_py)
        selector.show()
        app.exec()



