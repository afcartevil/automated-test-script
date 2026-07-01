import os
import time
from abc import abstractmethod, ABC
from typing import Union, Dict, Any, Optional


class DataCollectNode(ABC):
    """
    通用数据采集节点基类，无平台依赖
    """
    def __init__(self, name: str, params: Dict[str, Any]):
        self.name = name
        self.params = params

    def get_param(self, override_params: Optional[Dict[str, Any]], key: str, default_value=None):
        if override_params:
            ret = override_params.get(key)
            if ret is not None:
                return ret
        return self.params.get(key, default_value)

    @abstractmethod
    def collect(self, override_params: Optional[Dict[str, Any]] = None) -> Union[str, bytes]:
        """执行采集并返回原始数据"""
        pass

    def _on_post_collect(self, override_params: Optional[Dict[str, Any]]):
        post_wait = self.get_param(override_params, 'post_wait', 0)
        if post_wait > 0:
            time.sleep(post_wait)

    def save(self, data: Union[str, bytes], output_dir: str) -> str:
        os.makedirs(output_dir, exist_ok=True)
        ext = 'txt' if isinstance(data, str) else 'bin'
        path = os.path.join(output_dir, f"{self.name}.{ext}")
        mode = 'w' if isinstance(data, str) else 'wb'
        with open(path, mode) as f:
            f.write(data)
        return path

    def execute(self, output_dir: str, override_params: Optional[Dict[str, Any]] = None) -> str:
        data = self.collect(override_params)
        self._on_post_collect(override_params)
        return self.save(data, output_dir)
