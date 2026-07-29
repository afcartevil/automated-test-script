from typing import Optional

import pytest


class LinkPretestHelper:
    def __init__(self, pytest_item_node: pytest.Item):
        super().__init__()
        self._pytest_item = pytest_item_node
        self._case_short_name = pytest_item_node.name[5:]
        _config_dict: Optional[dict] = self.get_link_pretest_dict(pytest_item_node)
        if _config_dict is None:
            self.is_config_available = False
            self.config_dict = {}
        else:
            self.is_config_available = True
            self.config_dict = _config_dict

    @staticmethod
    def get_link_pretest_dict(node: pytest.Item) -> Optional[dict]:
        m = node.get_closest_marker('link_pretest')
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
    def case_short_name(self):
        return self._case_short_name

    @property
    def flag(self):
        return self.config_dict.get('flag', '')

    @property
    def flags(self):
        f = self.flag
        if not f:
            return tuple()
        if isinstance(f, str):
            return (f,)
        return f

    @property
    def name(self):
        return self.config_dict.get('name', '')

    @property
    def names(self):
        n = self.name
        if not n:
            return tuple()
        if isinstance(n, str):
            return (n,)
        return n
