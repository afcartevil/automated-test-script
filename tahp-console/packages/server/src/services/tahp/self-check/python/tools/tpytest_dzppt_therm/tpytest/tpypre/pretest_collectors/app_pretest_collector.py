from typing import List

import pytest

from tpytest.tpypre.pretest_collectors.pretest_collector import PretestCollector
from tpytest.tpypre.pretest_config_helper import PretestConfigHelper
from tpytest.tpypre.pretest_runtime import PretestRuntime


class AppPretestCollector(PretestCollector):
    def __init__(self, name: str, pretest_runtime: PretestRuntime, collect_pretest_categories: List[str], collect_ranges=None):
        super().__init__(name, pretest_runtime, collect_pretest_categories, collect_ranges)
        self._need_apps = None

    @property
    def need_apps(self):
        if self._need_apps is None:
            self._need_apps = set((app_info.id for app_info in self.scheme_env.test_apps))
        return self._need_apps

    def on_case_filter(self, item: pytest.Item, pretest_config_helper: PretestConfigHelper) -> bool:
        # 检查是否是pretest类并且具备自动收集预测试App的能力
        if item.parent:
            parent_cls = getattr(item.parent, 'cls', None)
            if not parent_cls:
                return False
            is_pretest_class = getattr(parent_cls, 'is_pretest_class', None)
            if not is_pretest_class:
                return False
            auto_collect_pretest_app = getattr(parent_cls, 'auto_collect_test_app_pretest', None)
            if not auto_collect_pretest_app:
                return False

        if not super().on_case_filter(item, pretest_config_helper):
            return False

        m = item.get_closest_marker('test_app')
        if not m:
            return False
        apps = [a.lower() for a in m.args]
        for a in apps:
            if a in self.need_apps:
                break
        else:
            return False
        return True
