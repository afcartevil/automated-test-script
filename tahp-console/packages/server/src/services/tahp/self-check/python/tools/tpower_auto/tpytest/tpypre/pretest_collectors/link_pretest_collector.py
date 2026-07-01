from typing import List

import pytest

from tpytest.tpypre.pretest_collectors.pretest_collector import PretestCollector
from tpytest.tpypre.pretest_config_helper import PretestConfigHelper
from tpytest.tpypre.pretest_runtime import PretestRuntime


class LinkPretestCollector(PretestCollector):
    def __init__(self, name: str, pretest_runtime: PretestRuntime, collect_pretest_categories: List[str], collect_ranges=None):
        super().__init__(name, pretest_runtime, collect_pretest_categories, collect_ranges)
        self._need_pretest_names = None
        self._need_pretest_flags = None

    @property
    def need_pretest_names(self):
        if self._need_pretest_names is None:
            self._need_pretest_names = self.scheme_env.collected_pretest_names
        return self._need_pretest_names

    @property
    def need_pretest_flags(self):
        if self._need_pretest_flags is None:
            self._need_pretest_flags = self.scheme_env.collected_pretest_flags
        return self._need_pretest_flags

    def on_case_filter(self, item: pytest.Item, pretest_config_helper: PretestConfigHelper) -> bool:
        if not super().on_case_filter(item, pretest_config_helper):
            return False

        if pretest_config_helper.case_name in self.need_pretest_names or (pretest_config_helper.flag and (pretest_config_helper.flag in self.need_pretest_flags)):
            return True

        return False
