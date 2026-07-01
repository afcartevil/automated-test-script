from tpytest.scheme.scheme_user_config import SchemeUserConfig


class Dou3Config(SchemeUserConfig):
    def __init__(self):
        self.is_whole_device_test = False
        self.usb_disconnect_mode = 'manual'
        self.case_area = ''
        super().__init__()

    def _fill_fields(self):
        super()._fill_fields()
        self.is_whole_device_test = bool(self.config_dict['is_whole_device_test'])
        self.usb_disconnect_mode = self.config_dict['usb_disconnect_mode']
        self.case_area = self.config_dict.get('case_area', '')

    @property
    def case_area_or_set(self):
        return self.case_area or self.case_set
