from tests.dzppt.dou3.dou3_config import Dou3Config
from powertrde.framework import t_inject
from powertrde.utils.feishu.feishu_api_helper import FeishuApiHelper
from powertrde.framework.table.feishu_static_table_loader import FeishuStaticTableLoader

class GlobalConfig():
    def __new__(cls, *args, **kwargs):
        if not hasattr(cls, 'instance'):
            cls.instance = super(GlobalConfig, cls).__new__(cls)
        return cls.instance
    
    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._feishu_helper: FeishuApiHelper = None
            self._feishu_static_table_loader: FeishuStaticTableLoader = None
            self._phone_infos: dict = None
            self._area_infos: dict = None
            self._table_apps: dict = None
            self._test_apps: dict = None
            self._back_apps: dict = None
            self._feishu_static_table_loader = None
            self._feishu_helper = None
            t_inject.configure(self._bind_injections)
            self._initialized = True
    
    def _bind_injections(self, binder: t_inject.Binder):
        binder.bind_to_constructor(FeishuApiHelper, lambda: self.feishu_helper)
        binder.bind_to_constructor(FeishuStaticTableLoader, lambda: self.feishu_static_table_loader)

    @property
    def feishu_helper(self):
        if self._feishu_helper is None:
            assert self.user_config.feishu_app_id and self.user_config.feishu_app_secret
            self._feishu_helper = FeishuApiHelper(self.user_config.feishu_app_id, self.user_config.feishu_app_secret)
            for name, token in self.user_config.feishu_root_table_tokens.items():
                self._feishu_helper.register_table_group_token(name, token)
                if name == 'default':
                    self._feishu_helper.register_table_group_token('', token)
            for name, token in self.user_config.feishu_root_folder_tokens.items():
                self._feishu_helper.register_root_folder_token(name, token)
                if name == 'default':
                    self._feishu_helper.register_root_folder_token('', token)
        return self._feishu_helper

    @property
    def feishu_static_table_loader(self):
        if self._feishu_static_table_loader is None:
            self._feishu_static_table_loader = FeishuStaticTableLoader(self.feishu_helper)
        return self._feishu_static_table_loader

    @property
    def user_config(self):
        return Dou3Config.get_instance()

    @property
    def test_apps(self):
        # 如果_test_apps为空，从table_apps中筛选出test_apps
        if not self._test_apps:
            testapps="AiGallery,YouTubeMusic,VishaVideoPlayer,CandyCrushSaga,\
                YouTube,Instagram,TikTok,MxPlayer,Facebook"
            self._test_apps: dict = {
                app: self.table_apps.get(app)
                for app in testapps.split(',')
                if self.table_apps.get(app) is not None}
        return self._test_apps

    @property
    def back_apps(self):
        if not self._back_apps:
            area_set = self.user_config.case_area_or_set
            backapps=self.area_infos[area_set]['back_apps']
            self._back_apps: dict = {
                app: self.table_apps.get(app)
                for app in backapps.split(',')
                if self.table_apps.get(app) is not None}
        return self._back_apps

    @property
    def res_provider(self):
        return self.user_config.res_provider
    
    @property
    def is_overseas(self):
        return self.user_config.test_region and self.user_config.test_region != 'CN'
        
    @property
    def phone_infos(self):
        if self._phone_infos is None:
            self._phone_infos = self.feishu_static_table_loader.load_table('dou3/table_dou3_products.xlsx')
        return self._phone_infos
        
    @property
    def area_infos(self):
        if self._area_infos is None:
            self._area_infos = self.feishu_static_table_loader.load_table('dou3/table_dou3_test_area.xlsx')
        return self._area_infos

    @property
    def table_apps(self):
        if self._table_apps is None:
            self._table_apps = self.feishu_static_table_loader.load_table('table_apps.xlsx')
        return self._table_apps

    @property
    def feishu_static_table_loader(self) -> FeishuStaticTableLoader:
        if self._feishu_static_table_loader is None:
            self._feishu_static_table_loader = FeishuStaticTableLoader(self.feishu_helper)
        return self._feishu_static_table_loader
    
    @property
    def feishu_helper(self):
        if self._feishu_helper is None:
            assert self.user_config.feishu_app_id and self.user_config.feishu_app_secret
            self._feishu_helper = FeishuApiHelper(self.user_config.feishu_app_id, self.user_config.feishu_app_secret)

            for name, token in self.user_config.feishu_root_table_tokens.items():
                self._feishu_helper.register_table_group_token(name, token)
                if name == 'default':
                    self._feishu_helper.register_table_group_token('', token)

            for name, token in self.user_config.feishu_root_folder_tokens.items():
                self._feishu_helper.register_root_folder_token(name, token)
                if name == 'default':
                    self._feishu_helper.register_root_folder_token('', token)

        return self._feishu_helper
    
    def get_brightness_with_area_set(self, device_model: str):
        if device_model not in self.phone_infos:
            raise Exception(f'The phone model {device_model} cannot be found in the product table.')
        info = self.phone_infos[device_model]
        area_set = self.user_config.case_area_or_set
        if f"{area_set}_bl" not in info:
            raise Exception(f'The area set {area_set} cannot be found in the product table.')
        return info[f"{area_set}_bl"]
    
    def get_volume_with_area_set(self, device_model: str):
        if device_model not in self.phone_infos:
            raise Exception(f'The phone model {device_model} cannot be found in the product table.')
        info = self.phone_infos[device_model]
        area_set = self.user_config.case_area_or_set
        if f"{area_set}_vol" not in info:
            raise Exception(f'The area set {area_set} cannot be found in the product table.')
        return info[f"{area_set}_vol"]