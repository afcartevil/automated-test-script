from typing import Optional, Dict, Any, Union

from data_collector.data_collect_node import DataCollectNode


class DummyCollectNode(DataCollectNode):
    """
    该收集节点只做模拟收集，同时提供等待时间的功能，可以加在一些采集节点中间作为等待使用
    params: {'post_wait'}
    """
    def collect(self, override_params: Optional[Dict[str, Any]] = None) -> Union[str, bytes]:
        return ''

    def save(self, data: Union[str, bytes], output_dir: str) -> str:
        return ''
