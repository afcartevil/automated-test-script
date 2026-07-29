from typing import Optional, List

import pytest


def get_pytest_node_exclude_collect(node: pytest.Item) -> bool:
    m = node.get_closest_marker('exclude_collect')
    return bool(m)


def get_pytest_node_case_config(node: pytest.Item) -> Optional[dict]:
    m = node.get_closest_marker('case_config')
    if m:
        if m.kwargs is not None:
            return dict(m.kwargs)
        return {}
    else:
        return {}


def get_pytest_node_test_apps(node: pytest.Item) -> Optional[List[str]]:
    m = node.get_closest_marker('test_app')
    if m:
        if m.args is not None:
            return list(m.args)
        return []
    else:
        return []


def get_pytest_node_copilot_apps(node: pytest.Item) -> Optional[List[str]]:
    m = node.get_closest_marker('copilot_app')
    if m:
        if m.args is not None:
            return list(m.args)
        return []
    else:
        return []
