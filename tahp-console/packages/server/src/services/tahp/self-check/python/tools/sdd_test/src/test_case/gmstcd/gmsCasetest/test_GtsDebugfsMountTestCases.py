# -*- coding: utf-8 -*-
import pytest
import logging

from data.res_list import CARRIAR_MARKETS
from src.utils.adb.adb_utils import (
    adb_shell,
)


def test_DebugfsMount(device_serial):
    """
    # GMS-VSR-3.4.4-001.001
    # DESCRIPTION: [GTS]GtsDebugfsMountTestCases-com.google.android.debugfsmount.gts.GtsDebugfsMountTestCases#testDebugfsMount
    测试运行时挂载状态，检查系统是否挂载了 debugfs
    """
    logging.info("开始测试: testDebugfsMount")

    # 检查 /proc/mounts 中是否有 debugfs 挂载
    result = adb_shell(device_serial, "cat /proc/mounts | grep debugfs")
    
    # 断言结果
    if not result["success"] or not result["output"]:
        logging.info("测试通过 (PASS): 系统未挂载 debugfs")
    else:
        logging.error(f"测试失败 (FAIL): 发现 debugfs 被挂载！输出内容: {result['output']}")
        pytest.fail(f"发现 debugfs 被挂载！输出内容: {result['output']}")



