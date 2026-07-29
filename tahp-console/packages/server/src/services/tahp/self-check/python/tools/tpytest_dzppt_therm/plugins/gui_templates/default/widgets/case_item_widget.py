from gui_templates.default.gui_options import GuiOptions
from qt_extends.base_q_ui import BaseQWidget


class CaseItemWidget(BaseQWidget):
    def __init__(self):
        super().__init__()
        self._ui_binder = GuiOptions.instance.case_item_ui_binder_class()
        self._ui_binder.setupUi(self)

        self.vm = GuiOptions.instance.case_item_vm_class()
        self.vm.bound_widget = self

        self._bind_view_models()

    def _bind_view_models(self):
        try:
            self.vm.bind_case_name(self._ui_binder.caseNameLabel)
        except Exception:
            pass
        try:
            self.vm.bind_case_desc(self._ui_binder.caseDescLabel)
        except Exception:
            pass
        try:
            self.vm.bind_case_status(self._ui_binder.caseStatusLabel)
        except Exception:
            pass
        try:
            self.vm.bind_time_text(self._ui_binder.caseTimeLabel)
        except Exception:
            pass
