from typing import Protocol

from PyQt6.QtWidgets import QMainWindow, QWidget


class BaseUI:
    pass


class QUIBinder(Protocol):
    def setupUi(self, ui_auto_gen):
        pass

    def retranslateUi(self, ui_auto_gen):
        pass


class BaseQUI(BaseUI):
    def __init__(self):
        super().__init__()
        self._ui_binder = None

    @property
    def ui_binder(self) -> QUIBinder:
        return self._ui_binder


class BaseQWindow(BaseQUI, QMainWindow):
    pass


class BaseQWidget(BaseQUI, QWidget):
    pass
