#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fetch task_base list from Feishu table for UI selection."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def setup_env() -> None:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    plugins = ROOT / "plugins"
    if plugins.is_dir() and str(plugins) not in sys.path:
        sys.path.insert(0, str(plugins))
    os.chdir(ROOT)


def fetch_task_base() -> list[dict]:
    """Fetch task_base list from Feishu table."""
    setup_env()
    
    # Import dependencies
    try:
        from powertrde.utils.feishu.feishu_api_helper import FeishuApiHelper
        from powertrde.framework.table.feishu_static_table_loader import FeishuStaticTableLoader
    except ImportError as e:
        return {"ok": False, "message": f"导入飞书表格加载器失败: {e}", "tasks": []}
    
    try:
        # Use production token
        token_table = 'HQl0sE40dhBFvctZCP9cv5uHnYc'
        powercloud_app_id = 'cli_a81049d61c2c900e'
        powercloud_app_secret = 'foH623pzGZeYOaVJB8POedMDQxQP0qb4'
        
        feishu_ins = FeishuApiHelper(powercloud_app_id, powercloud_app_secret)
        feishu_ins.register_table_group_token('powercloudcfg', token_table)
        loader = FeishuStaticTableLoader(feishu_ins)
        tasks = loader.load_table('powercloudcfg/task_base')
        
        if not tasks:
            return {"ok": True, "message": "task_base 为空", "tasks": []}
        
        # Convert to list of dicts with key fields, filter out WhatsApp tasks
        task_list = []
        for task_id, task_data in tasks.items():
            case_id = task_data.get("case_id", "")
            # 跳过 WhatsApp 相关测试
            if "whatsapp" in case_id.lower():
                continue
            task_list.append({
                "task_id": task_id,
                "case_id": case_id,
                "task": task_data.get("task", ""),
                "priority": task_data.get("priority", ""),
            })
        
        # Sort by task_id
        task_list.sort(key=lambda x: x.get("task_id", ""))
        
        return {"ok": True, "message": f"获取到 {len(task_list)} 个任务", "tasks": task_list}
    except Exception as e:
        return {"ok": False, "message": f"获取 task_base 失败: {e}", "tasks": []}


def main() -> int:
    result = fetch_task_base()
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
