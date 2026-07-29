import os
from typing import List, Dict, Any, Optional

from data_collector.data_collect_node_factory import DataCollectNodeFactory
from powertrde.framework.tran_logger import t_log
from powertrde.utils.trde.trde_utils import ADB_EXE


class DataNodeCollector:
    """
    调度执行：支持 configs, device_id, adb_path，并可通过 label 在 output_dir 下创建子文件夹
    """
    def __init__(self, configs: List[Dict[str, Any]], output_dir: str,
                 device_id: Optional[str] = None, adb_path: str = ADB_EXE):
        self.configs = configs
        self.output_dir = output_dir
        self.device_id = device_id
        self.adb_path = adb_path

    def run_all(self, label: Optional[str] = None, override_params: Optional[Dict[str, Any]] = None) -> List[str]:
        """
        执行所有采集节点。
        :param label: 子文件夹名称，若指定则在 output_dir 下创建此子目录用于保存结果
        :return: 所有保存的文件路径列表
        """
        # 确定目标目录
        target_dir = self.output_dir
        if label:
            target_dir = os.path.join(self.output_dir, label)
        os.makedirs(target_dir, exist_ok=True)

        # 动态创建节点并执行
        results = []
        for cfg in self.configs:
            try:
                node = DataCollectNodeFactory.create(
                    cfg['type'], cfg['name'], cfg.get('params', {}),
                    device_id=self.device_id, adb_path=self.adb_path
                )
                path = node.execute(target_dir, override_params=override_params)
                results.append(path)
            except Exception as e:
                t_log.error(f"Error in collect node '{cfg.get('name')}': {e}")
        return results


# 示例
if __name__ == '__main__':
    _configs = [
        {'type': 'android_cmd', 'name': 'meminfo', 'params': {'shell_cmd': 'cat /proc/meminfo1'}},
        # {'type': 'android_cmd', 'name': 'current_window', 'params': {'shell_cmd': '"dumpsys window | grep Current"'}},
        {'type': 'android_pull', 'name': 'tpytest_env', 'params': {'remote_path': '/sdcard/dz_auto_env.zip1'}},
        # {'type': 'android_logcat', 'name': 'logcat', 'params': {'filterspec': '*:E', 'clear': True}}
    ]
    from powertrde.utils.trde import adb

    collector = DataNodeCollector(_configs, output_dir='D:\\1', device_id=adb.first_device())
    paths = collector.run_all(label='2025-07-09_16-10-55')
    print('Collected:', paths)
