from powertrde import env
from powertrde.framework.logs_protocol import logs_p
from powertrde.framework.table.default_static_table_loader import DefaultStaticTableLoader
from powertrde.framework.table.feishu_static_table_loader import FeishuStaticTableLoader
from powertrde.framework.table.table_manager import TableManager
from powertrde.framework import t_inject


class FeishuStaticTableLoaderInjectionFactory:
    def __call__(self, *args, **kwargs):
        _loader = None
        if not env.has_user_env_trunk_flag('use_feishu_static_table'):
            # 当禁止飞书表格时，强制使用本地表格加载器
            _loader = TableManager.get_instance().get_loader(DefaultStaticTableLoader)
            return _loader
        try:
            _loader = t_inject.instance(FeishuStaticTableLoader)
            _ = _loader.feishu_instance.access_token
            TableManager.get_instance().set_loader(_loader)
        except Exception as e:
            # 待改进为json缓存读取
            if env.has_user_env_trunk_flag('feishu_static_table_fallback_local'):
                logs_p().log_warning(f'Can not access feishu loader, will fallback to local table loader! details: {e}')
                _loader = TableManager.get_instance().get_loader(DefaultStaticTableLoader)
            else:
                raise
        return _loader
