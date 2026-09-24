"""P1 驱动自检执行脚本。

使用方法:
    python run_p1_check.py [设备序列号] [手势状态]

参数:
    设备序列号: ADB 设备序列号（可选，自动检测第一个设备）
    手势状态: "全闭" 或 "全开"（默认：全闭）

示例:
    python run_p1_check.py
    python run_p1_check.py ABC123456
    python run_p1_check.py ABC123456 全开
"""
import sys
import os
import subprocess
from pathlib import Path

# 添加项目路径
script_dir = Path(__file__).parent
sys.path.insert(0, str(script_dir))


def get_adb_devices():
    """获取已连接的 ADB 设备列表。"""
    try:
        result = subprocess.run(
            ["adb", "devices"],
            capture_output=True,
            text=True,
            timeout=10
        )
        devices = []
        for line in result.stdout.strip().split("\n")[1:]:
            if line.strip() and "device" in line:
                serial = line.split()[0]
                devices.append(serial)
        return devices
    except Exception as e:
        print(f"获取 ADB 设备失败: {e}")
        return []


def step_update(text):
    """打印步骤更新。"""
    print(f"[步骤] {text}")


def main():
    # 解析参数
    serial = None
    gesture_state = "全闭"

    if len(sys.argv) > 1:
        serial = sys.argv[1]
    if len(sys.argv) > 2:
        gesture_state = sys.argv[2]

    # 如果没有指定设备，自动检测
    if not serial:
        print("正在检测 ADB 设备...")
        devices = get_adb_devices()
        if not devices:
            print("错误: 未检测到 ADB 设备，请连接设备后重试")
            print("提示: 使用 'adb devices' 检查设备连接")
            sys.exit(1)
        serial = devices[0]
        print(f"自动选择设备: {serial}")

    print(f"\n{'='*60}")
    print(f"P1 驱动自检")
    print(f"{'='*60}")
    print(f"设备序列号: {serial}")
    print(f"手势状态: {gesture_state}")
    print(f"{'='*60}\n")

    # 导入并执行测试
    try:
        from cases.power_feature.p1_check import case1

        device_info = {"deviceId": serial}

        print("开始执行 P1 驱动自检...\n")

        result = case1.run(
            device_info=device_info,
            step_update=step_update,
            gesture_state=gesture_state
        )

        print(f"\n{'='*60}")
        print(f"测试结果")
        print(f"{'='*60}")
        print(f"状态: {result.get('status', 'unknown').upper()}")
        print(f"消息: {result.get('message', '')}")
        print(f"{'='*60}")

        # 返回退出码
        if result.get("status") == "pass":
            sys.exit(0)
        else:
            sys.exit(1)

    except ImportError as e:
        print(f"错误: 无法导入测试模块 - {e}")
        sys.exit(1)
    except Exception as e:
        print(f"错误: 执行测试失败 - {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
