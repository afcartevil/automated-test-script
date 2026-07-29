#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import subprocess
import sys
from datetime import datetime

def _validate_copilot_list(main_device, copilot_list):
    """返回(合规列表, 不合规原因字典)。合规：在线、非主测机、指针位置开启。"""
    validated = []
    reasons = {}
    seen = set()

    for sn in copilot_list:
        s = str(sn).strip()
        if not s:
            reasons[s] = "空 SN"
            continue
        if s in seen:
            reasons[s] = "重复 SN"
            continue
        if s == str(main_device).strip():
            reasons[s] = "不能与主测机相同"
            continue
        validated.append(s)
        seen.add(s)
    return validated, reasons


def push_pairing_config(main_device, copilot_devices, description="测试机与辅助机配对关系"):
    """推送设备配对配置到测试机

    输入支持单个或列表；
    写入 JSON 字段：
    - copilot_device_ids: 合规辅助机列表（按顺序优先）
    """
    # 归一化辅助机ID输入
    copilot_list = copilot_devices if isinstance(copilot_devices, (list, tuple)) else [copilot_devices]
    copilot_list = [str(x) for x in copilot_list if x]

    # 合规校验与过滤
    validated, reasons = _validate_copilot_list(main_device, copilot_list)
    if not validated:
        print("❌ 未找到合规的辅助机；请检查 SN。")
        for sn, reason in reasons.items():
            if sn:
                print(f"- {sn}: {reason}")
        return False

    # 创建配置（仅列表字段）
    config = {
        "copilot_device_ids": validated,
        "main_device": str(main_device).strip(),
        "created_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "description": description
    }

    # 保存临时文件
    temp_file = "temp_pairing.json"
    with open(temp_file, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    try:
        # 推送到设备
        result = subprocess.run([
            "adb", "-s", str(main_device).strip(), "push",
            temp_file, "/sdcard/device_pairing.json"
        ], capture_output=True, text=True)

        if result.returncode == 0:
            print(f"✅ 配对配置已推送到 {main_device}")
            print(f"主测机: {main_device}")
            print(f"辅助机(合规): {validated}")
            if reasons:
                print("ℹ️ 以下候选未写入：")
                for sn, reason in reasons.items():
                    if sn and sn not in validated:
                        print(f"- {sn}: {reason}")
            return True
        else:
            print(f"❌ 推送失败: {result.stderr}")
            return False

    except Exception as e:
        print(f"❌ 错误: {e}")
        return False
    finally:
        # 清理临时文件
        import os
        if os.path.exists(temp_file):
            os.remove(temp_file)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python device_pairing_setup.py <主测机SN> <辅助机SN1> <辅助机SN2>....... [描述]")
        print("示例: python device_pairing_setup.py 1A2B3C4D 5E6F7G8H 8Z9X0Y1W")
        sys.exit(1)

    main_device = sys.argv[1]
    copilot_devices = sys.argv[2:]
    description = "测试机与辅助机配对关系"

    success = push_pairing_config(main_device, copilot_devices, description)
    sys.exit(0 if success else 1)