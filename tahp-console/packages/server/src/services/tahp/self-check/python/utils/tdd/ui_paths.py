"""测试 UI dump / 坐标缓存路径（统一写入 result_dir/ui/<device_id>/）。"""

import re
from pathlib import Path
from typing import Optional

UI_SUBDIR = "ui"

_result_dir: Optional[Path] = None


def set_ui_result_dir(result_dir) -> None:
    """绑定本轮测试结果目录；dump 与 ui.json 缓存均写入其下 ui/ 子目录。"""
    global _result_dir
    if result_dir:
        resolved = Path(result_dir).resolve()
        (resolved / UI_SUBDIR).mkdir(parents=True, exist_ok=True)
        _result_dir = resolved
    else:
        _result_dir = None


def get_ui_result_dir() -> Optional[Path]:
    return _result_dir


def sanitize_device_id(device_id: str) -> str:
    sanitized = re.sub(r'[<>:"/\\|?*]', "_", device_id or "").strip()
    return sanitized or "unknown_device"


def device_ui_dir(device_id: str) -> Path:
    if _result_dir is None:
        raise RuntimeError(
            "未设置测试结果目录，无法保存 UI dump。测试启动时应调用 set_ui_result_dir。"
        )
    path = _result_dir / UI_SUBDIR / sanitize_device_id(device_id)
    path.mkdir(parents=True, exist_ok=True)
    return path
