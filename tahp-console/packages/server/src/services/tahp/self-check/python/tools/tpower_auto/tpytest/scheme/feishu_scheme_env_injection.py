from powertrde.framework.table.feishu_static_table_loader import FeishuStaticTableLoader
from powertrde.framework import t_inject
from powertrde.utils.feishu.feishu_api_helper import FeishuApiHelper
from tpytest.scheme.scheme_user_config import SchemeUserConfig


class FeishuSchemeEnvInjection:
    def __init__(self):
        self._feishu_helper = None
        self._feishu_static_table_loader = None
        self.binder_factories.append(self._feishu_bind_injections)
        super().__init__()

    @property
    def binder_factories(self):
        raise NotImplementedError

    @property
    def user_config(self) -> SchemeUserConfig:
        raise NotImplementedError

    @property
    def feishu_helper(self):
        if self._feishu_helper is None:
            assert self.user_config.feishu_app_id and self.user_config.feishu_app_secret
            self._feishu_helper = FeishuApiHelper(self.user_config.feishu_app_id, self.user_config.feishu_app_secret)
        return self._feishu_helper

    @property
    def feishu_static_table_loader(self):
        if self._feishu_static_table_loader is None:
            assert self.user_config.feishu_scheme_table_token
            self._feishu_static_table_loader = FeishuStaticTableLoader(self.feishu_helper, self.user_config.feishu_scheme_table_token)
        return self._feishu_static_table_loader

    def _feishu_bind_injections(self, binder: t_inject.Binder):
        binder.bind_to_constructor(FeishuApiHelper, lambda: self.feishu_helper)
        binder.bind_to_constructor(FeishuStaticTableLoader, lambda: self.feishu_static_table_loader)
