from typing import Optional, Dict, Any

from data_collector.android.android_collect_node import AndroidCollectNode


class AndroidLogcatNode(AndroidCollectNode):
    """
    通过 adb logcat -d 采集日志，支持清空
    params: {'filterspec', 'clear'}
    """
    def collect(self, override_params: Optional[Dict[str, Any]] = None) -> str:
        fs = self.get_param(override_params, 'filterspec', '')
        args = ['logcat', '-d']
        if fs:
            args += ['-s', fs]
        out = self.run_cmd(*args)
        if self.get_param(override_params, 'clear', False):
            self.run_cmd('logcat -c', capture=False)
        return out
