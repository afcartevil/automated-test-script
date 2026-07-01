import io
import os
import re
from contextlib import redirect_stdout
from datetime import datetime
from typing import List, Callable, Optional, Union, Dict

import pytest

from tpytest.case_original_request import CaseOriginalRequest


###############################################################################
# 第一部分：用于预收集所有测试项的插件
###############################################################################

class CollectPlugin:
    """
    自定义插件，用于在收集阶段收集所有测试用例项。
    """

    def __init__(self):
        self.collected_items = []

    def pytest_collection_modifyitems(self, session, config, items):
        self.collected_items.extend(items)


###############################################################################
# 第二部分：用于正式执行时对测试项重新排序和复制的插件
###############################################################################

class ScheduledOrderItem:
    def __init__(self, abs_node_id: str, case_ori_request: CaseOriginalRequest, test_item: pytest.Item):
        self.abs_node_id = abs_node_id
        self.case_ori_request = case_ori_request
        self.test_item = test_item


class SchedulerPlugin:
    """
    调度插件，根据预先生成的调度顺序列表重新排序测试项，
    并对重复出现的测试项进行克隆处理，保证重复执行。

    参数：
      scheduled_order: list[str]
          预先生成的调度顺序列表，每项都是一个测试项的绝对 nodeid，
          如 "/abs/path/to/test_file.py::TestClass::test_method"，
          列表中可能存在重复项。
    """

    def __init__(self, scheduled_order_items: List[ScheduledOrderItem]):
        self.scheduled_order_items: List[ScheduledOrderItem] = scheduled_order_items

    def pytest_collection_modifyitems(self, session, config, items):
        # 构造一个字典：键为绝对 nodeid，值为列表（所有匹配到的测试项）
        mapping = {}
        for item in items:
            abs_nodeid = self._get_abs_nodeid(item)
            mapping.setdefault(abs_nodeid, []).append(item)

        new_items = []
        # 记录每个 scheduled_nodeid 已使用次数
        usage = {}

        for order_item in self.scheduled_order_items:
            scheduled_nodeid = order_item.abs_node_id
            usage_count = usage.get(scheduled_nodeid, 0)
            if scheduled_nodeid in mapping:
                items_list = mapping[scheduled_nodeid]
                if usage_count < len(items_list):
                    # 使用已有的测试项
                    item = items_list[usage_count]
                    if order_item.case_ori_request.retry != 0:
                        # 检查是否已有 flaky 标记
                        for mark in list(item.iter_markers(name="flaky")):
                            item.own_markers.remove(mark)  # 移除旧的 flaky 标记
                        if order_item.case_ori_request.retry > 0:
                            # 添加你自己的 flaky 标记（覆盖原有的）
                            item.add_marker(pytest.mark.flaky(reruns=order_item.case_ori_request.retry, reruns_delay=0))
                    else:
                        retry_mark = item.get_closest_marker('retry')
                        if retry_mark and retry_mark.args:
                            for mark in list(item.iter_markers(name="flaky")):
                                item.own_markers.remove(mark)
                            item.add_marker(pytest.mark.flaky(reruns=int(retry_mark.args[0]), reruns_delay=0))
                else:
                    # 如果已有的测试项不够，则重新生成一个新的测试项
                    original_item = items_list[0]
                    cls = type(original_item)
                    # 通过 from_parent 生成新项
                    new_item = cls.from_parent(
                        parent=original_item.parent,
                        name=original_item.name,
                        callobj=original_item.obj,
                    )
                    # 将原始的 fixture 信息复制过去，确保 fixture 能正常工作
                    new_item._fixtureinfo = original_item._fixtureinfo
                    new_item.fixturenames = original_item.fixturenames
                    new_node_id = scheduled_nodeid + '_'
                    if order_item.case_ori_request.dup_index > 1:
                        new_node_id += f'_d{order_item.case_ori_request.dup_index}'
                    if order_item.case_ori_request.big_loop_index > 1:
                        new_node_id += f'_b{order_item.case_ori_request.big_loop_index}'
                    if order_item.case_ori_request.loop_index > 1:
                        new_node_id += f'_s{order_item.case_ori_request.loop_index}'
                    new_item._nodeid = new_node_id
                    item = new_item

                    if order_item.case_ori_request.retry != 0:
                        for mark in list(item.iter_markers(name="flaky")):
                            item.own_markers.remove(mark)
                        if order_item.case_ori_request.retry > 0:
                            item.add_marker(pytest.mark.flaky(reruns=order_item.case_ori_request.retry, reruns_delay=0))
                    else:
                        retry_mark = item.get_closest_marker('retry')
                        if retry_mark and retry_mark.args:
                            for mark in list(item.iter_markers(name="flaky")):
                                item.own_markers.remove(mark)
                            item.add_marker(pytest.mark.flaky(reruns=int(retry_mark.args[0]), reruns_delay=0))

                item.original_request = order_item.case_ori_request
                usage[scheduled_nodeid] = usage_count + 1
                new_items.append(item)
            else:
                raise ValueError(f"Node not found in the collection during scheduling: {scheduled_nodeid}")

        # 替换 pytest 收集到的 items 列表
        items[:] = new_items

    def _get_abs_nodeid(self, item):
        """
        将收集到的 item 的 nodeid 文件部分转换为绝对路径，
        如将 "dzppt/dou3/scenes/test_dou3_scenes.py::TestDou3Scenes::test_dou3_facebook_browse"
        转换为 "/abs/path/dzppt/dou3/scenes/test_dou3_scenes.py::TestDou3Scenes::test_dou3_facebook_browse"
        """
        parts = item.nodeid.split("::")
        abs_path = os.path.abspath(str(item.path))
        return "::".join([abs_path] + parts[1:])


###############################################################################
# 第三部分：调度器实现
###############################################################################

class TPytestTestScheduler:
    """
    Pytest 测试方法调度器

    参数：
      case_test_requests: Union[List[str], List[CaseOriginalRequest]]
          需求方给定的测试方法名称列表（允许重复），如：
          ["test_case_a", "test_case_b", "test_case_a"]
      如果 case_ori_requests == ['*'] 表示收集所有测试用例。
      test_ranges: list[str]
          测试用例范围（目录、模块或文件），如：["tests/"] 或 ["module1.py", "tests/"]
    """

    def __init__(self, case_test_requests: Union[List[str], List[CaseOriginalRequest]], test_ranges: List[str],
                 custom_filter: Optional[Callable[[pytest.Item], bool]] = None):
        self.case_ori_requests: List[CaseOriginalRequest] = self._convert_case_ori_requests(case_test_requests)
        self.test_ranges = test_ranges
        self.custom_filter: Optional[Callable[[pytest.Item], bool]] = custom_filter
        self.pre_collected_items: List[pytest.Item] = []  # 用于预收集的 pytest.Item 列表
        self.scheduled_order_items: List[ScheduledOrderItem] = []  # 最终生成的调度顺序
        self._scheduled_item_defined_count: Dict[str, int] = {}
        self.one_loop_scheduled_items: List[ScheduledOrderItem] = []  # 非大循环的调度顺序用例
        self._already_applied_loops = 0
        self.last_start_time: Optional[datetime] = None
        self.last_end_time: Optional[datetime] = None

    def _gain_scheduled_item_defined_count(self, abs_node_id: str):
        exist_count = self._scheduled_item_defined_count.get(abs_node_id, 0)
        exist_count += 1
        self._scheduled_item_defined_count[abs_node_id] = exist_count
        return exist_count

    @staticmethod
    def _convert_case_ori_requests(case_test_requests: Union[List[str], List[CaseOriginalRequest]]):
        if case_test_requests is None:
            return []
        if len(case_test_requests) > 0 and isinstance(case_test_requests[0], str):
            return CaseOriginalRequest.parse_lines(case_test_requests)
        else:
            return case_test_requests

    def pre_collect_tests(self, disable_output=False):
        """
        利用 --collect-only 模式收集所有测试项，用于后续生成调度顺序列表。
        """
        plugin = CollectPlugin()
        pytest_args = list(self.test_ranges) + ["--collect-only"]
        captured_output = None
        if disable_output:
            with io.StringIO() as f, redirect_stdout(f):
                ret = pytest.main(pytest_args, plugins=[plugin])
                captured_output = f.getvalue()
        else:
            ret = pytest.main(pytest_args, plugins=[plugin])
        if ret != 0:
            # 0 = all good, 5 = no tests collected
            any_details = '' if not captured_output else f" details here: {captured_output}"
            raise RuntimeError(
                f"Pre-collected test cases failed. Please check if the incoming test scope is correct. Or some use case code may have static compilation errors.{any_details}")
        self.pre_collected_items = plugin.collected_items

    def pre_collect_single_test(self, nodeid: str, disable_output: bool = False):
        """
        只收集并返回单条用例对应的 Item 列表（长度 0 或 1）。
        nodeid 格式：path/to/test_file.py::TestClass::test_method
        """
        plugin = CollectPlugin()
        pytest_args = [nodeid, "--collect-only"]
        if disable_output:
            buf = io.StringIO()
            with redirect_stdout(buf):
                ret_code = pytest.main(pytest_args, plugins=[plugin])
            output = buf.getvalue()
        else:
            ret_code = pytest.main(pytest_args, plugins=[plugin])
            output = None

        if ret_code != 0:
            # 0 = all good, 5 = no tests collected
            msg = f"collect_single_test Return unexpected exit code: {ret_code}"
            if output:
                msg += f"\ndetails here:\n{output}"
            raise RuntimeError(msg)
        self.pre_collected_items = plugin.collected_items
        if len(self.pre_collected_items) > 1:
            self.pre_collected_items = self.pre_collected_items[:1]

    def clear_pre_collected_items(self):
        self.pre_collected_items.clear()

    def clear_scheduled_items(self):
        self.scheduled_order_items.clear()
        self.one_loop_scheduled_items.clear()
        self._already_applied_loops = 0

    def generate_schedule(self, big_loop: int = 1):
        """
        根据传入的 case_ori_requests，在预收集的测试项中查找匹配，
        生成调度顺序列表（绝对 nodeid 列表）。
        规则：
          - 对于 case_ori_requests 中的每个测试方法名称，深度搜索预收集测试项，
            匹配条件：item.nodeid 最后部分（方法名）等于给定名称。
          - 如果找到则将其绝对 nodeid（通过 _convert_to_abs_nodeid）添加到调度顺序列表。
          - 如果同一方法名称在列表中出现多次，后续项也将添加进去，
            但正式执行阶段将根据这个列表进行克隆处理，从而实现重复运行。
        """
        if not self.pre_collected_items:
            raise RuntimeError("The pre-collected test cases are empty. Please execute pre_collect_tests() first.")

        # 通配符：收集所有
        if len(self.case_ori_requests) == 1 and self.case_ori_requests[0].case_id == "*":
            request = self.case_ori_requests[0]
            for item in self.pre_collected_items:
                if item.get_closest_marker('exclude_collect') or (self.custom_filter and not self.custom_filter(item)):
                    continue
                abs_nodeid = self._convert_to_abs_nodeid(item)
                dup_index = self._gain_scheduled_item_defined_count(abs_nodeid)
                for i in range(request.loop * request.group_loop):
                    self.one_loop_scheduled_items.append(
                        ScheduledOrderItem(abs_nodeid,
                                           request.clone_with_indexes(len(self.scheduled_order_items) + 1, dup_index, 1,
                                                                      i + 1),
                                           item)
                    )
        else:
            for request in self.case_ori_requests:
                # —— 新增：如果 whole_class=True，则收集该类下所有方法 ——
                if request.whole_class:
                    # 从 nodeid 中提取类名（倒数第二段）
                    matched = [
                        item for item in self.pre_collected_items
                        if item.nodeid.split("::")[-2] == request.case_id and not item.get_closest_marker('exclude_collect') and (not self.custom_filter or self.custom_filter(item))
                    ]
                    if not matched:
                        raise ValueError(f"No test methods found for class '{request.case_id}'")
                    for i in range(request.group_loop):
                        for item in matched:
                            abs_nodeid = self._convert_to_abs_nodeid(item)
                            if i == 0:
                                dup_index = self._gain_scheduled_item_defined_count(abs_nodeid)
                            else:
                                dup_index = self._scheduled_item_defined_count.get(abs_nodeid)
                            for j in range(request.loop):
                                self.one_loop_scheduled_items.append(
                                    ScheduledOrderItem(abs_nodeid,
                                                       request.clone_with_indexes(len(self.scheduled_order_items) + 1,
                                                                                  dup_index,
                                                                                  1, i * j + 1), item)
                                )
                elif request.regex:
                    # 正则匹配：匹配完整 nodeid（文件::类::方法）
                    pattern = re.compile(request.case_id)
                    matched = [
                        item for item in self.pre_collected_items
                        if pattern.search(item.nodeid) and not item.get_closest_marker('exclude_collect') and (not self.custom_filter or self.custom_filter(item))
                    ]
                    if not matched:
                        raise ValueError(f"No test methods matching regex：{request.case_id}")
                    for i in range(request.group_loop):
                        for item in matched:
                            abs_nodeid = self._convert_to_abs_nodeid(item)
                            if i == 0:
                                dup_index = self._gain_scheduled_item_defined_count(abs_nodeid)
                            else:
                                dup_index = self._scheduled_item_defined_count.get(abs_nodeid)
                            for j in range(request.loop):
                                self.one_loop_scheduled_items.append(
                                    ScheduledOrderItem(abs_nodeid,
                                                       request.clone_with_indexes(len(self.scheduled_order_items) + 1,
                                                                                  dup_index,
                                                                                  1, i * j + 1), item)
                                )
                else:
                    # 原有：单条用例匹配
                    found_item: Optional[pytest.Item] = None
                    for item in self.pre_collected_items:
                        node_name = item.nodeid.rsplit("::", 1)[-1]
                        if node_name == request.case_id and (not self.custom_filter or self.custom_filter(item)):
                            found_item = item
                            break
                    if not found_item:
                        raise ValueError(f"No test methods found in pre-collection phase：{request.case_id}")
                    abs_nodeid = self._convert_to_abs_nodeid(found_item)
                    dup_index = self._gain_scheduled_item_defined_count(abs_nodeid)
                    for i in range(request.loop * request.group_loop):
                        self.one_loop_scheduled_items.append(
                            ScheduledOrderItem(abs_nodeid,
                                               request.clone_with_indexes(len(self.scheduled_order_items) + 1,
                                                                          dup_index, 1, i + 1), found_item)
                        )
                    # 更精准的匹配方式，但是用处估计不大，而且会增加计算负担，先注释
                    # segs = request.case_id.split("::")
                    # method_name = segs[-1]
                    # prefix_segs = segs[:-1]
                    # found_item = None
                    # for item in self.pre_collected_items:
                    #     parts = item.nodeid.split("::")
                    #     file_path = parts[0]
                    #     item_method = parts[-1]
                    #     # 1) 方法名必须匹配
                    #     if item_method != method_name:
                    #         continue
                    #     # 2) 前缀多段匹配
                    #     if prefix_segs:
                    #         class_name = parts[-2] if len(parts) > 2 else None
                    #         ok = True
                    #         for seg in reversed(prefix_segs):
                    #             if class_name and seg == class_name:
                    #                 continue
                    #             if file_path.endswith(seg):
                    #                 continue
                    #             ok = False
                    #             break
                    #         if not ok:
                    #             continue
                    #     # 3) 自定义过滤
                    #     if self.custom_filter and not self.custom_filter(item):
                    #         continue
                    #     # 找到第一个符合的，立即退出
                    #     found_item = item
                    #     break
                    # if not found_item:
                    #     raise ValueError(f"No test methods found in pre-collection phase：{request.case_id}")
                    # abs_nodeid = self._convert_to_abs_nodeid(found_item)
                    # for _ in range(int(request.loop * request.group_loop)):
                    #     self._one_loop_scheduled_items.append(
                    #         ScheduledOrderItem(abs_nodeid, request, found_item)
                    #     )
        self._already_applied_loops = 1
        self.scheduled_order_items = self.one_loop_scheduled_items
        if big_loop > 1:
            self.apply_scheduled_items_loop(big_loop)

    def clip_scheduled_items_interval(self, interval_start: float, interval_end: float):
        total = len(self.scheduled_order_items)
        # 计算截取索引
        start_idx = int(total * interval_start)
        end_idx = int(total * interval_end)
        # 截取并替换
        self.scheduled_order_items = self.scheduled_order_items[start_idx:end_idx]

    def apply_scheduled_items_loop(self, big_loop: int):
        if big_loop > 1:
            self._already_applied_loops = big_loop
            self.scheduled_order_items = []
            for i in range(big_loop):
                for j in range(len(self.one_loop_scheduled_items)):
                    item = self.one_loop_scheduled_items[j]
                    if i > 0:
                        item = ScheduledOrderItem(item.abs_node_id, item.case_ori_request.clone_with_indexes(
                            len(self.scheduled_order_items) + 1, item.case_ori_request.dup_index, i + 1,
                            item.case_ori_request.loop_index), item.test_item)
                    self.scheduled_order_items.append(item)

    def _convert_to_abs_nodeid(self, item):
        """
        同 SchedulerPlugin._get_abs_nodeid 实现一致
        """
        parts = item.nodeid.split("::")
        abs_path = os.path.abspath(str(item.path))
        return "::".join([abs_path] + parts[1:])

    def start(self, **kwargs):
        """
        调度器一键启动：
          1. 预收集测试用例
          2. 根据 method_names 生成调度顺序列表
          3. 正式执行时传入测试范围，并利用 SchedulerPlugin 重排序和复制测试项，
             以达到按指定顺序（含重复）运行测试的目的
        """
        # print("【预收集阶段】开始收集测试用例……")
        # self.pre_collect_tests()
        # print(f"预收集到 {len(self.collected_items)} 个测试用例。")

        # print("【调度阶段】生成调度顺序……")
        # self.generate_schedule()
        # print("调度顺序生成如下：")
        # for idx, node in enumerate(self.scheduled_order, start=1):
        #     print(f"  {idx}: {node}")

        self.last_start_time = datetime.now()

        # 构造 pytest 命令行参数数组，包括测试范围和自定义参数
        pytest_args = self.test_ranges + [f'--{key}={value}' for key, value in kwargs.items()]

        # print("【执行阶段】启动 pytest 执行测试……")
        # 这里不传 nodeid 参数，而是传入测试范围，同时将 SchedulerPlugin 传入 pytest
        ret_code = pytest.main(pytest_args, plugins=[SchedulerPlugin(self.scheduled_order_items)])

        self.last_end_time = datetime.now()
        if ret_code > 1:
            raise RuntimeError(f'Pytest execute failed with exit code {ret_code}, please see logs for more details.')

    @property
    def last_test_duration(self):
        if not self.last_start_time or not self.last_end_time:
            return 0.0
        return (self.last_end_time - self.last_start_time).total_seconds()

    @staticmethod
    def find_first_test_node(root: str, method_name: str) -> Optional[str]:
        """
        在给定的根目录下快速搜索第一个名为 `method_name` 的测试方法，并返回相对路径的 pytest 节点标识：
          <subpath/to/file.py>::<ClassName>::<method_name>
        :param root: 搜索根目录，如 'test/dzppt/dou3'
        :param method_name: 测试方法名，例如 'test_mock_1'
        :return: 相对路径节点或 None
        """
        method_pattern = re.compile(rf'^\s*def\s+{re.escape(method_name)}\s*\(')
        class_pattern = re.compile(r'^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)')
        root = os.path.normpath(root)
        for dirpath, dirnames, filenames in os.walk(root):
            # 跳过缓存
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for fname in filenames:
                if not (fname.startswith("test_") and fname.endswith(".py")):
                    continue
                full_path = os.path.join(dirpath, fname)
                current_class = None
                with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                    for line in f:
                        m_cls = class_pattern.match(line)
                        if m_cls:
                            current_class = m_cls.group(1)
                            continue
                        if method_pattern.match(line):
                            # 构造 pytest 节点
                            rel_file = os.path.relpath(full_path, root).replace(os.sep, '/')
                            if current_class:
                                node = f"{rel_file}::{current_class}::{method_name}"
                            else:
                                node = f"{rel_file}::{method_name}"
                            return node
        return None


###############################################################################
# 第四部分：示例入口
###############################################################################

if __name__ == "__main__":
    # 示例：假设需求方要求按如下顺序执行测试方法，允许重复（注意：方法名称必须与测试用例中最后部分完全一致）
    test_method_names = [
        "test_dou3_facebook_browse",
        "test_dou3_facebook_browse"  # 重复执行
    ]

    # 示例：测试范围（请根据实际情况修改）
    os.chdir('..')
    _test_ranges = ["tests/"]

    _scheduler = TPytestTestScheduler(case_test_requests=test_method_names, test_ranges=_test_ranges)
    _scheduler.start()
