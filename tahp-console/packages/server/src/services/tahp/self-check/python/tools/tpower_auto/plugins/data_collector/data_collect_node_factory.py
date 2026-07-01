from typing import Type, Dict, Any, Optional

from data_collector.android.android_app_info_node import AndroidAppInfoNode
from data_collector.android.android_cmd_node import AndroidCmdNode
from data_collector.android.android_collect_node import AndroidCollectNode
from data_collector.android.android_file_pull_node import AndroidFilePullNode
from data_collector.android.android_logcat_node import AndroidLogcatNode
from data_collector.data_collect_node import DataCollectNode
from data_collector.dummy_collect_node import DummyCollectNode
from powertrde.utils.trde.trde_utils import ADB_EXE


class DataCollectNodeFactory:
    registry: Dict[str, Type[DataCollectNode]] = {}

    @classmethod
    def register(cls, node_type: str, node_cls: Type[DataCollectNode]):
        cls.registry[node_type] = node_cls

    @classmethod
    def create(cls, node_type: str, name: str, params: Dict[str, Any],
               device_id: Optional[str] = None, adb_path: str = ADB_EXE) -> DataCollectNode:
        node_cls = cls.registry.get(node_type)
        if not node_cls:
            raise ValueError(f"Unknown node type: {node_type}")
        # Android 类型
        if issubclass(node_cls, AndroidCollectNode):
            return node_cls(name, params, device_id=device_id, adb_path=adb_path)
        # 通用或本地
        return node_cls(name, params)


# 注册节点
DataCollectNodeFactory.register('dummy', DummyCollectNode)
DataCollectNodeFactory.register('android_cmd', AndroidCmdNode)
DataCollectNodeFactory.register('android_pull', AndroidFilePullNode)
DataCollectNodeFactory.register('android_logcat', AndroidLogcatNode)
DataCollectNodeFactory.register('android_appinfo', AndroidAppInfoNode)
