import os
from typing import Union, Optional, Dict, Any

from data_collector.android.android_collect_node import AndroidCollectNode


class AndroidFilePullNode(AndroidCollectNode):
    """
    支持 pull 获取设备文件内容
    params: {'remote_path'}
    """

    def collect(self, override_params: Optional[Dict[str, Any]] = None) -> Union[str, bytes]:
        raise NotImplementedError('This class will not implement this method, please do not call it.')

    def execute(self, output_dir: str, override_params: Optional[Dict[str, Any]] = None) -> str:
        rp = self.get_param(override_params, 'remote_path')
        ext = os.path.basename(rp)
        filename = f"{self.name}__{ext}" if self.name != ext else self.name
        dest = os.path.join(output_dir, filename)
        os.makedirs(output_dir, exist_ok=True)
        # 直接 pull 到 dest
        self.run_pull(rp, dest)
        self._on_post_collect(override_params)
        return dest
