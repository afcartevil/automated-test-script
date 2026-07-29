from typing import TypeVar

from powertrde.framework.table.static_info import StaticInfo
from tpytest_extends.scheme.feishu_injection_factory import FeishuStaticTableLoaderInjectionFactory

T = TypeVar('T', bound=StaticInfo)


class CopilotStaticInfo(StaticInfo):
    default_load_file = 'copilot_devices.xlsx'
    default_table_loader_or_factory = FeishuStaticTableLoaderInjectionFactory()
    convert_to_lower_key = True

    def __init__(self):
        super().__init__()
        self._finally_linked_info = None

        self._phone_number1 = ''
        self._phone_number2 = ''
        self._whatsapp_account = ''
        self._facebook_account = ''

    @property
    def phone_number1(self):
        return self._phone_number1

    @property
    def phone_number2(self):
        return self._phone_number1

    @property
    def whatsapp_account(self):
        return self._whatsapp_account

    @property
    def facebook_account(self):
        return self._facebook_account

    def __repr__(self):
        return self.ori_id

    def __str__(self):
        return self.ori_id

    def _on_assign_field(self, filed_name: str, value) -> bool:
        if filed_name == 'phone_number1':
            self._phone_number1 = value
            return True
        elif filed_name == 'phone_number2':
            self._phone_number1 = value
            return True
        elif filed_name == 'whatsapp_account':
            self._whatsapp_account = value
            return True
        elif filed_name == 'facebook_account':
            self._facebook_account = value
            return True

    @staticmethod
    def get_copilot_info(copilot_sn: str) -> 'CopilotStaticInfo':
        ret = CopilotStaticInfo.get_default_table().get_info(copilot_sn)
        return ret

    def get_account_dict(self):
        """
        新增账号类型时，这里需要加入，未自动收集property
        """
        default = {}
        for account in ['phone_number1', 'phone_number2', 'whatsapp_account', 'facebook_account']:
            acc_v = eval(f'self.{account}')
            if acc_v and acc_v != "-":
                default[account] = acc_v
        return default


