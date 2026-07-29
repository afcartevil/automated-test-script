from powertrde.framework.table.static_info import StaticInfo
from tpytest_extends.scheme.feishu_injection_factory import FeishuStaticTableLoaderInjectionFactory


class PhoneStaticInfo(StaticInfo):
    default_load_file = 'table_phone.xlsx'
    default_table_loader_or_factory = FeishuStaticTableLoaderInjectionFactory()
    convert_to_lower_key = True

    def __init__(self):
        super().__init__()
        self.battery_capacity = 0
        self.has_caller_sensor = False
        self.curved_screen = False
        self.a_z_mode = {}
        self.is_low_end = False