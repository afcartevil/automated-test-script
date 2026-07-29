from gui_templates.default.default_gui_constants import DefaultGuiConstants


class ThermGuiConstants(DefaultGuiConstants):
    DEFAULT_VERSION = '1.0.0'
    SCHEME_NAME = 'therm'
    GUI_DISPLAY_TITLE = '温升检查策略执行器'
    WINDOW_TITLE_CMD = 'THERM CMD'
    WINDOW_TITLE_GUI = 'THERM GUI'

    @classmethod
    def get_sop_link(cls):
        sop_link = {
            'link': 'https://transsioner.feishu.cn/wiki/Akohw8apliHABjk3HuqcmpltnVh',
            'name': '温升策略检测自动化1.0-SOP',
        }
        return sop_link
