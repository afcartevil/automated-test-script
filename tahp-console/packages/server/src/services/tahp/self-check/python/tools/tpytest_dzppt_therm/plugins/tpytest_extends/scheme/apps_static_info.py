import copy
import re
from typing import Dict, Optional, List

from powertrde import env
from powertrde.framework.table.static_info import StaticInfo
from powertrde.utils.feishu.feishu_api_helper import FeishuApiHelper
from tpytest_extends.scheme.feishu_injection_factory import FeishuStaticTableLoaderInjectionFactory


class AppsStaticInfo(StaticInfo):
    default_load_file = 'table_apps.xlsx'
    default_table_loader_or_factory = FeishuStaticTableLoaderInjectionFactory()
    convert_to_lower_key = True

    def __init__(self):
        super().__init__()
        self._package = ''
        self._search_name = ''
        self._icon_name = ''
        self._default_variant_device_sn = ''
        self._finally_linked_info = None
        self._more_icon_names: List[str] = []
        self.other_packages: Dict[str, str] = {}
        self.other_search_names: Dict[str, str] = {}
        self.other_icon_names: Dict[str, str] = {}
        self.other_link_ids: Dict[str, str] = {}
        self.other_more_icon_names: Dict[str, List[str]] = {}
        self.default_link_id: str = ''
        self.launch_time = 0.0
        self.type = ''
        self.overseas_card = False
        self.vpn_cn = False
        self.full_screen = False
        self.no_update = False

    def __repr__(self):
        return self.ori_id

    def __str__(self):
        return self.ori_id

    @property
    def linked_info(self):
        if self._finally_linked_info is None:
            self._finally_linked_info = self.get_finally_link_info_by_user_env_config(variant_device_sn=self._default_variant_device_sn)
        return self._finally_linked_info

    @property
    def linked_id(self):
        return self.linked_info.ori_id

    @property
    def icon_name(self):
        return self.icon_names[0]

    @property
    def icon_names(self):
        return self.get_icon_names_by_user_env_config(variant_device_sn=self._default_variant_device_sn)

    @property
    def package(self):
        return self.get_package_by_user_env_config(variant_device_sn=self._default_variant_device_sn)

    @property
    def search_name(self):
        return self._split_search_name_and_index(self.get_search_name_by_user_env_config(variant_device_sn=self._default_variant_device_sn))[0]

    @property
    def search_index(self):
        return self._split_search_name_and_index(self.get_search_name_by_user_env_config(variant_device_sn=self._default_variant_device_sn))[1]

    def set_search_index(self, index: int):
        _self = self.linked_info
        g_pos = _self._search_name.find('[')
        if g_pos > 0:
            _self._search_name = _self.search_name[:g_pos]
        _self._search_name = f'{_self._search_name}[{index}]'

    @staticmethod
    def _split_search_name_and_index(search_name: str):
        n = search_name
        i = 0
        g_pos = search_name.find('[')
        if g_pos > 0:
            i = int(search_name[g_pos + 1:search_name.index(']', g_pos + 1)])
            n = search_name[:g_pos]
        return n, i

    @staticmethod
    def get_app_info(app_name: str, variant_device_sn: str = '') -> 'AppsStaticInfo':
        ret = AppsStaticInfo.get_default_table().get_info(app_name)
        if variant_device_sn and variant_device_sn != env.get_user_env_arg('device_sn'):
            ret = copy.copy(ret)
            ret._default_variant_device_sn = variant_device_sn
        return ret

    @staticmethod
    def get_app_info_no_raise(app_name: str, variant_device_sn: str = '') -> Optional['AppsStaticInfo']:
        ret = AppsStaticInfo.get_default_table().get_info_with_default(app_name, None)
        if not ret:
            return ret
        if variant_device_sn and variant_device_sn != env.get_user_env_arg('device_sn'):
            ret = copy.copy(ret)
            ret._default_variant_device_sn = variant_device_sn
        return ret

    @staticmethod
    def get_app_package_by_name(app_name: str, variant_device_sn: str = '') -> str:
        return AppsStaticInfo.get_app_info(app_name, variant_device_sn).package

    def _on_assign_field(self, filed_name: str, value: str) -> bool:
        if filed_name == 'package':
            self._package = FeishuApiHelper.wash_hyperlink_texts_to_plain_text(value)
            return True
        elif filed_name == 'other_packages':
            _text_value = FeishuApiHelper.wash_hyperlink_texts_to_plain_text(value)
            for sub_item in (s.strip() for s in re.split(r'[;\n]+', _text_value)):
                splits = sub_item.split(':')
                if len(splits) < 2:
                    continue
                for ss in splits[0].split(','):
                    self.other_packages[ss.strip()] = splits[1]
            return True
        elif filed_name == 'other_search_names':
            for sub_item in (s.strip() for s in re.split(r'[;\n]+', value)):
                splits = sub_item.split(':')
                if len(splits) < 2:
                    continue
                for ss in splits[0].split(','):
                    self.other_search_names[ss.strip()] = splits[1]
            return True
        elif filed_name == 'other_icon_names':
            for sub_item in (s.strip() for s in re.split(r'[;\n]+', value)):
                splits = sub_item.split(':')
                if len(splits) < 2:
                    continue
                for ss in splits[0].split(','):
                    self.other_icon_names[ss.strip()] = splits[1]
            return True
        elif filed_name == 'more_icon_names':
            for sub_item in (s.strip() for s in re.split(r'[;\n]+', value)):
                splits = sub_item.split(':')
                if len(splits) < 2:
                    if splits:
                        _sss = splits[0].strip()
                        if _sss and _sss != '-':
                            self._more_icon_names = [_s.strip() for _s in splits[0].split(',')]
                    continue
                for ss in splits[0].split(','):
                    self.other_more_icon_names[ss.strip()] = [_s.strip() for _s in splits[1].split(',')]
            return True
        elif filed_name == 'other_link_ids':
            for sub_item in (s.strip() for s in re.split(r'[;\n]+', value)):
                splits = sub_item.split(':')
                if len(splits) < 2:
                    continue
                for ss in splits[0].split(','):
                    _k = ss.strip()
                    self.other_link_ids[_k] = splits[1]
                    if _k.lower() == 'default':
                        self.default_link_id = splits[1]
            return True
        elif filed_name == 'search_name':
            self._search_name = value
            return True
        elif filed_name == 'icon_name':
            self._icon_name = value
            if self._icon_name == '-' or not self._icon_name:
                self._icon_name = self.ori_id
            return True
        return False

    def _on_assign_fields_finished(self, origin_fields_dict: dict):
        super()._on_assign_fields_finished(origin_fields_dict)
        if not self._search_name or self._search_name == '-':
            self._search_name = self.ori_id

        if self._icon_name not in self._more_icon_names:
            self._more_icon_names.insert(0, self._icon_name)

        for _k, _v in self.other_icon_names.items():
            if _k not in self.other_more_icon_names:
                self.other_more_icon_names[_k] = [_v]
            elif _v not in self.other_more_icon_names[_k]:
                self.other_more_icon_names[_k].insert(0, _v)

    @classmethod
    def get_app_multi_package_keys(cls, variant_device_sn: str = '') -> Optional[List[str]]:
        if not variant_device_sn:
            variant_device_sn = env.get_user_env_arg('device_sn')
        base = env.get_user_env_arg('app_multi_package_keys')
        update = None
        if variant_device_sn:
            update = env.get_user_env_arg(f'app_multi_package_keys_{variant_device_sn}')
        ret = list()
        if base:
            ret.extend(base)
        if update:
            for u in update:
                if u not in base:
                    ret.append(u)
        return ret

    def get_package_by_user_env_config(self, variant_device_sn: str = ''):
        _self = self.linked_info
        return _self.get_package_by_keys(_self.get_app_multi_package_keys(variant_device_sn))

    def get_search_name_by_user_env_config(self, variant_device_sn: str = ''):
        _self = self.linked_info
        return _self.get_search_name_by_keys(_self.get_app_multi_package_keys(variant_device_sn))

    def get_icon_names_by_user_env_config(self, variant_device_sn: str = ''):
        _self = self.linked_info
        return _self.get_icon_names_by_keys(_self.get_app_multi_package_keys(variant_device_sn))

    def get_link_info_by_user_env_config(self, variant_device_sn: str = ''):
        if not self.other_link_ids:
            return self
        return self.get_link_info_by_keys(self.get_app_multi_package_keys(variant_device_sn))

    def get_finally_link_info_by_user_env_config(self, variant_device_sn: str = ''):
        if not self.other_link_ids:
            return self
        i = self
        while True:
            j = i.get_link_info_by_keys(self.get_app_multi_package_keys(variant_device_sn))
            if j is i:
                return j
            i = j

    def get_closest_variant_key(self, variant_device_sn_or_default=''):
        keys = self.get_app_multi_package_keys(variant_device_sn_or_default or self._default_variant_device_sn)
        keys = keys[::-1]
        for key in keys:
            p = self.other_link_ids.get(key)
            if p:
                return key
        for key in keys:
            p = self.other_packages.get(key)
            if p:
                return key
        return ''

    def get_package_by_key(self, key: Optional[str]):
        _self = self.linked_info
        if not key:
            return _self._package
        p = _self.other_packages.get(key)
        if not p:
            p = _self._package
        return p

    def get_package_by_keys(self, keys: Optional[List[str]]):
        _self = self.linked_info
        return _self.get_package_and_key_by_keys(keys)[0]

    def get_package_and_key_by_keys(self, keys: Optional[List[str]]):
        _self = self.linked_info
        if not keys:
            return _self._package, ''
        if isinstance(keys, str):
            key = str(keys)
            return _self.get_package_by_key(key), key
        for key in reversed(keys):
            p = _self.other_packages.get(key)
            if p:
                return p, key
        return _self._package, ''

    def get_search_name_by_key(self, key: Optional[str]):
        _self = self.linked_info
        if not key:
            return _self._search_name
        p = _self.other_search_names.get(key)
        if not p:
            p = _self._search_name
        return p

    def get_search_name_by_keys(self, keys: Optional[List[str]]):
        _self = self.linked_info
        if not keys:
            return _self._search_name
        if isinstance(keys, str):
            return _self.get_search_name_by_key(str(keys))
        for key in reversed(keys):
            p = _self.other_search_names.get(key)
            if p:
                return p
        return _self._search_name

    def get_icon_names_by_key(self, key: Optional[str]):
        _self = self.linked_info
        if not key:
            return _self._more_icon_names
        p = _self.other_more_icon_names.get(key)
        if not p:
            p = _self._more_icon_names
        return p

    def get_icon_names_by_keys(self, keys: Optional[List[str]]):
        _self = self.linked_info
        if not keys:
            return _self._more_icon_names
        if isinstance(keys, str):
            return _self.get_icon_names_by_key(str(keys))
        for key in reversed(keys):
            p = _self.other_more_icon_names.get(key)
            if p:
                return p
        return _self._more_icon_names

    def get_default_link_info(self):
        if not self.default_link_id:
            return self
        p_info = self.get_app_info_no_raise(self.default_link_id)
        return p_info or self

    def get_link_info_by_key(self, key: Optional[str]):
        if not key:
            return self.get_default_link_info()
        p = self.other_link_ids.get(key)
        if not p:
            return self.get_default_link_info()
        p_info = self.get_app_info_no_raise(p)
        return p_info or self.get_default_link_info()

    def get_link_info_by_keys(self, keys: Optional[List[str]]):
        if not keys:
            return self.get_default_link_info()
        if isinstance(keys, str):
            return self.get_link_info_by_key(str(keys))
        for key in reversed(keys):
            p = self.other_link_ids.get(key)
            if not p:
                continue
            p_info = self.get_app_info_no_raise(p)
            if p_info:
                return p_info
        return self.get_default_link_info()
