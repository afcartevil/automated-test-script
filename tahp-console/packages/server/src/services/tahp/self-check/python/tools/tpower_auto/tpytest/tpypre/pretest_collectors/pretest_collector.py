from typing import List

import pytest

from tpytest.tpypre.pretest_config_helper import PretestConfigHelper
from tpytest.tpypre.pretest_runtime import PretestRuntime
from tpytest.tpytest_scheduler import TPytestTestScheduler


class PretestCollector:
    def __init__(self, name: str, pretest_runtime: PretestRuntime, collect_pretest_categories: List[str], collect_ranges=None):
        self.name = name
        self.collect_categories = collect_pretest_categories
        self.pretest_runtime = pretest_runtime
        if collect_ranges is None:
            collect_ranges = [f'tests/{self.scheme_env.scheme_request.team}/{self.scheme_env.scheme_request.name}/']
        elif isinstance(collect_ranges, str):
            collect_ranges = [collect_ranges]
        elif isinstance(collect_ranges, list) and not collect_ranges:
            collect_ranges = [f'tests/{self.scheme_env.scheme_request.team}/{self.scheme_env.scheme_request.name}/']
        self.test_scheduler = TPytestTestScheduler(
            case_test_requests=['*'],
            test_ranges=collect_ranges
        )

    @property
    def scheme_env(self):
        return self.pretest_runtime.scheme_env

    def on_case_filter(self, item: pytest.Item, pretest_config_helper: PretestConfigHelper) -> bool:
        # 检查是否是pretest类
        if item.parent:
            parent_cls = getattr(item.parent, 'cls', None)
            if not parent_cls:
                return False
            is_pretest_class = getattr(parent_cls, 'is_pretest_class', None)
            if not is_pretest_class:
                return False

        # 检查类别是否符合
        if self.collect_categories and pretest_config_helper.category not in self.collect_categories:
            return False

        # 检查等级是否符合
        if pretest_config_helper.level_compare_method == 'equal':
            if pretest_config_helper.level != self.scheme_env.user_config.pretest_level:
                return False
        else:
            if pretest_config_helper.level > self.scheme_env.user_config.pretest_level:
                return False

        # 检查时效是否符合（是否曾经测试通过）
        if self.pretest_runtime.is_target_pretest_pass(pretest_config_helper.target, pretest_config_helper.case_short_name, pretest_config_helper.expiration_duration):
            return False

        return True

    def collect(self, clear_pre_collected_items=True):
        self.test_scheduler.clear_scheduled_items()
        if clear_pre_collected_items:
            self.test_scheduler.clear_pre_collected_items()
            self.test_scheduler.pre_collected_items = list(self.pretest_runtime.pre_collected_pretest_items)
        self.test_scheduler.custom_filter = lambda _i: self.on_case_filter(_i, PretestConfigHelper(_i))
        self.test_scheduler.generate_schedule()

        if self.test_scheduler.scheduled_order_items:
            self.test_scheduler.scheduled_order_items.sort(key=lambda x: PretestConfigHelper(x.test_item).order)
            self.scheme_env.pretest_counter.extend_case_infos(self.test_scheduler.scheduled_order_items)
            self.scheme_env.logger.info(f"{self.__class__.__name__}-{self.name} collected below pretest cases:")
            for idx, order_item in enumerate(self.test_scheduler.scheduled_order_items, 1):
                self.scheme_env.logger.info(f"{idx:02d} | {order_item.abs_node_id.split('/')[-1]}")
        else:
            self.scheme_env.logger.info(f"{self.__class__.__name__}-{self.name} collected ZERO pretest cases.")

    def execute(self):
        if not self.test_scheduler.pre_collected_items:
            raise Exception('Please collect cases first!')
        if self.test_scheduler.scheduled_order_items:
            self.test_scheduler.start()
