#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
cmd_quickedit.py - 控制 Windows CMD 的快速编辑模式

用法:
    python cmd_quickedit.py on    set_quick_edit(True)   # 开启快速编辑模式
    python cmd_quickedit.py off   set_quick_edit(False)  # 关闭快速编辑模式
    python cmd_quickedit.py status  get_quick_edit_status() # 查看当前状态
"""

import sys
import winreg

# 注册表路径：控制 CMD 快速编辑模式
REG_PATH = r"Console"
REG_NAME = "QuickEdit"

def set_quick_edit(enable: bool):
    """设置快速编辑模式"""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, REG_NAME, 0, winreg.REG_DWORD, 1 if enable else 0)
        print(f"✅ 已{'开启' if enable else '关闭'} CMD 快速编辑模式")
    except Exception as e:
        print(f"❌ 修改失败: {e}")

def get_quick_edit_status():
    """读取当前状态"""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, REG_NAME)
            print(f"🔍 当前快速编辑模式状态: {'开启' if value else '关闭'}")
    except FileNotFoundError:
        print("⚠️ 未设置过快速编辑模式（默认关闭）")
    except Exception as e:
        print(f"❌ 读取失败: {e}")

def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(0)

    cmd = sys.argv[1].lower()
    if cmd == "on":
        set_quick_edit(True)
    elif cmd == "off":
        set_quick_edit(False)
    elif cmd == "status":
        get_quick_edit_status()
    else:
        print("❌ 参数错误，应为 on/off/status")

if __name__ == "__main__":
    main()
