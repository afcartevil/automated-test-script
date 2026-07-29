class GuiOptions:
    instance = None

    @property
    def gui_constants_class(self):
        from gui_templates.default.default_gui_constants import DefaultGuiConstants
        return DefaultGuiConstants

    @property
    def gui_main_window_class(self):
        from gui_templates.default.default_gui_main_window import DefaultGuiMainWindow
        return DefaultGuiMainWindow

    @property
    def gui_main_vm_class(self):
        from gui_templates.default.vm.default_gui_main_vm import DefaultGuiMainVM
        return DefaultGuiMainVM

    @property
    def gui_main_vm_config_class(self):
        from gui_templates.default.vm.default_gui_main_vm import DefaultGuiMainVMConfig
        return DefaultGuiMainVMConfig

    @property
    def gui_runtime_vm_class(self):
        from gui_templates.default.vm.default_gui_runtime_vm import DefaultGuiRuntimeVM
        return DefaultGuiRuntimeVM

    @property
    def main_ui_binder_class(self):
        from gui_templates.default.ui.ui_default_gui_main_window import Ui_DefaultGuiMainWindow
        return Ui_DefaultGuiMainWindow

    @property
    def case_item_ui_binder_class(self):
        from gui_templates.default.ui.ui_default_gui_case_item import Ui_CaseItem
        return Ui_CaseItem

    @property
    def case_item_vm_class(self):
        from gui_templates.default.vm.case_item_vm import CaseItemVM
        return CaseItemVM

    @property
    def case_item_widget_class(self):
        from gui_templates.default.widgets.case_item_widget import CaseItemWidget
        return CaseItemWidget

    @property
    def case_scheme_sub_entry_class(self):
        raise NotImplementedError()

    @property
    def reporter_class(self):
        from tpytest.test_reporter import TestReporter
        return TestReporter

    @property
    def config_class(self):
        from tpytest.scheme.scheme_user_config import SchemeUserConfig
        return SchemeUserConfig

