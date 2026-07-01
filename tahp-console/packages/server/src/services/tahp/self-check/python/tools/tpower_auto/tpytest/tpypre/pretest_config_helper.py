from typing import Optional

import pytest


class PretestConfigHelper:
    def __init__(self, pytest_item_node: pytest.Item):
        super().__init__()
        self._pytest_item = pytest_item_node
        self._case_short_name = pytest_item_node.name[5:]
        _config_dict: Optional[dict] = self.get_pretest_config(pytest_item_node)
        if _config_dict is None:
            self.is_config_available = False
            self.config_dict = {}
        else:
            self.is_config_available = True
            self.config_dict = _config_dict

    @staticmethod
    def get_pretest_config(node: pytest.Item) -> Optional[dict]:
        m = node.get_closest_marker('pretest_config')
        if m:
            if m.kwargs is not None:
                return dict(m.kwargs)
            return {}
        else:
            return None

    @property
    def pytest_item(self):
        return self._pytest_item

    @property
    def case_name(self):
        return self._pytest_item.name

    @property
    def case_short_name(self):
        return self._case_short_name

    @property
    def flag(self):
        return self.config_dict.get('flag', '')

    @property
    def level(self):
        return self.config_dict.get('level', 0)

    @property
    def level_compare_method(self):
        return self.config_dict.get('level_compare', '')

    @property
    def expiration_duration(self):
        ret = self.config_dict.get('expiration', -1.0)
        if ret is None:
            return -1.0
        return ret

    @property
    def target(self):
        return self.config_dict.get('target', 'phone')

    @property
    def category(self):
        return self.config_dict.get('category', '')

    @property
    def order(self):
        return self.config_dict.get('order', 99999)
