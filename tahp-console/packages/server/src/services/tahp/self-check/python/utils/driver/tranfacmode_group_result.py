import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
import xml.etree.ElementTree as ET


def _prepare_environment() -> None:
    """
    与 start.py 保持一致：确保项目根目录在 sys.path 中。
    这样无论从根目录还是 test 目录运行脚本，都能 import utils.tdd.* 等模块。
    """
    root_dir = Path(__file__).resolve().parent.parent
    os.chdir(root_dir)
    root_str = str(root_dir)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)


_prepare_environment()

from utils.tdd.ui_automatic import dump_current_ui


PKG_PREFIX = "com.transsion.tranfacmode:id/"

RID_CURRENT_GROUP = PKG_PREFIX + "result_current_group_tv"
RID_GROUP_NAME = PKG_PREFIX + "result_group_item_name_tv"
RID_CONTAINER = PKG_PREFIX + "result_container"
RID_ITEM_NAME = PKG_PREFIX + "result_item_name_tv"
RID_STATE = PKG_PREFIX + "result_state_tv"

PASS_TEXTS = {"通过", "Pass", "PASS"}
FAIL_TEXTS = {"失败", "Fail", "FAIL"}


def _resource_id_endswith(node: ET.Element, rid: str) -> bool:
    full = (node.attrib.get("resource-id") or "").strip()
    if not full:
        return False
    return full == rid or full.endswith("/" + rid.split("/")[-1])


def _find_child_by_rid(parent: ET.Element, rid: str) -> Optional[ET.Element]:
    for node in parent.iter("node"):
        if _resource_id_endswith(node, rid):
            return node
    return None


def _node_text(node: Optional[ET.Element]) -> str:
    if node is None:
        return ""
    return (node.attrib.get("text") or "").strip()


def parse_current_group_results(xml_path: Path) -> Optional[Dict[str, Any]]:
    """
    从 tranfacmode 结果页面的 uiautomator XML 中解析当前测试组及其所有子项结果。

    返回结构:
    {
      "group": "屏幕",
      "items": [
        {"name": "1.1: 色彩", "state": "通过"},
        ...
      ],
      "all_pass": true,
      "has_fail": false
    }
    """
    if not xml_path.is_file():
        return None

    root = ET.parse(xml_path).getroot()
    nodes: List[ET.Element] = list(root.iter("node"))

    current_idx: Optional[int] = None
    for i, node in enumerate(nodes):
        if _resource_id_endswith(node, RID_CURRENT_GROUP):
            current_idx = i
            break

    if current_idx is None:
        return None

    group_name = ""
    header_idx: Optional[int] = None
    for j in range(current_idx, -1, -1):
        name_node = _find_child_by_rid(nodes[j], RID_GROUP_NAME)
        if name_node is not None:
            group_name = _node_text(name_node)
            header_idx = j
            break

    if header_idx is None or not group_name:
        return None

    items: List[Dict[str, str]] = []

    for node in nodes[header_idx + 1 :]:
        if _resource_id_endswith(node, RID_GROUP_NAME):
            break
        if not _resource_id_endswith(node, RID_CONTAINER):
            continue

        name_node = _find_child_by_rid(node, RID_ITEM_NAME)
        state_node = _find_child_by_rid(node, RID_STATE)
        name = _node_text(name_node)
        state = _node_text(state_node)
        if not name:
            continue

        items.append({"name": name, "state": state})

    if not items:
        return {
            "group": group_name,
            "items": [],
            "all_pass": False,
            "has_fail": False,
        }

    states = {it["state"] for it in items}
    all_pass = states.issubset(PASS_TEXTS)
    has_fail = any(s in FAIL_TEXTS for s in states)

    return {
        "group": group_name,
        "items": items,
        "all_pass": all_pass,
        "has_fail": has_fail,
    }


def get_current_group_results(device_id: str) -> Optional[Dict[str, Any]]:
    """
    使用 adb + uiautomator dump 当前界面，解析 tranfacmode 当前测试组结果。
    """
    xml_path = dump_current_ui(device_id)
    if xml_path is None:
        return None
    return parse_current_group_results(xml_path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="解析 tranfacmode 当前测试组及测试结果（基于 resource-id）。"
    )
    parser.add_argument(
        "device_id",
        help="adb 设备序列号，例如 0123456789ABCDEF",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="以缩进 JSON 格式输出结果",
    )
    args = parser.parse_args()

    result = get_current_group_results(args.device_id)
    if result is None:
        print("null")
        return

    if args.pretty:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()

