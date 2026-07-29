import re
from typing import Set, Optional

from powertrde.framework.table.static_info import StaticInfo
from powertrde.utils import confuse_utils
from powertrde.utils.feishu.feishu_api_helper import FeishuApiHelper
from tpytest_extends.scheme.feishu_injection_factory import FeishuStaticTableLoaderInjectionFactory


class AccountsStaticInfo(StaticInfo):
    default_load_file = 'table_accounts.xlsx'
    default_table_loader_or_factory = FeishuStaticTableLoaderInjectionFactory()
    convert_to_lower_key = True

    def __init__(self):
        super().__init__()
        self.schemes: Set[str] = set()
        self.target_devices: Set[str] = set()
        self.account_dict: dict = {}
        self.maintainer: str = ''

    def __repr__(self):
        return self.ori_id

    def __str__(self):
        return self.ori_id

    def default_account_dict(self) -> dict:
        return self.account_dict.get('default', {})

    def _on_assign_field(self, filed_name: str, value) -> bool:
        if filed_name == 'schemes':
            self.schemes.update(x.strip() for x in re.split('[,\n]', value) if x.strip())
            return True
        elif filed_name == 'target_devices':
            self.target_devices.update(x.strip() for x in re.split('[,\n]', value) if x.strip())
            return True
        return False

    def _on_assign_fields_finished(self, origin_fields_dict: dict):
        self.account_dict.clear()
        for k, v in origin_fields_dict.items():
            if k.startswith('a_'):
                _sub_account_info = self.parse_account_info_dict(v)
                if _sub_account_info:
                    self.account_dict[k[2:]] = _sub_account_info

    @staticmethod
    def parse_account_info_dict(text: str) -> Optional[dict]:
        """
        解析账号信息字典
        """
        text = text.strip()
        if not text or text == '-':
            return None
        text = FeishuApiHelper.wash_hyperlink_texts_to_plain_text(text)

        ret = {}
        _no_key_line_count = 0
        for ogi_line in text.split('\n'):
            line = ogi_line.strip()
            if not line:
                continue
            if ':' in line:
                k, v = line.split(':', 1)
                k = k.strip()
                v = v.strip()
                if k and v and k not in ret:
                    ret[k] = confuse_utils.defuse_string(v)
            else:
                _no_key_line_count += 1
                k = None
                if _no_key_line_count == 1:
                    k = 'account'
                elif _no_key_line_count == 2:
                    k = 'password'
                if k and k not in ret:
                    ret[k] = confuse_utils.defuse_string(line)
        return ret

