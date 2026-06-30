import os
import subprocess
import argparse
from src.utils.adb.adb_utils import get_first_sn
import pytest


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="运行测试用例")
    parser.add_argument(
        "-serial", "--serial", type=str, help="指定设备序列号，例如 ASALE3741B000022"
    )
    parser.add_argument("-vv", action="store_true", help="详细模式")
    parser.add_argument(
        "--tb",
        choices=["line", "short", "no", "native"],
        default="line",
        help="错误信息显示方式",
    )
    parser.add_argument(
        "--reruns",
        type=int,
        help="失败用例重跑次数（需安装 pytest-rerunfailures）",
    )
    parser.add_argument(
        "--reruns-delay",
        type=int,
        help="失败重跑间隔秒（需安装 pytest-rerunfailures）",
    )
    parser.add_argument(
        "--skip-spd-info",
        action="store_true",
        help="跳过获取SPD信息，仅收集/执行非SPD依赖流程",
    )
    # 可指定测试用例
    parser.add_argument("--testcase", type=str, help="指定测试用例，例如 test_case3.py")
    # 添加测试类型参数
    parser.add_argument(
        "--test-type",
        choices=["baseline", "performance", "gmstcd", "usd"],
        help="指定测试类型：baseline、performance、gmstcd 或 usd",
    )
    return parser.parse_args(argv)


def build_pytest_args(args):
    pytest_args = []

    # 根据参数确定测试路径
    if args.testcase:
        pytest_args.extend([args.testcase])
    elif args.test_type == "baseline":
        pytest_args.extend(["-rs", "src/test_case/baseline", "-vv"])
    elif args.test_type == "performance":
        pytest_args.extend(["-rs", "src/test_case/performance", "-vv"])
    elif args.test_type == "gmstcd":
        pytest_args.extend(["-rs", "src/test_case/gmstcd", "-vv"])
    elif args.test_type == "usd":
        pytest_args.extend(["-rs", "src/test_case/usd", "-vv"])
    else:
        pytest_args.extend(["-rs", "src", "-v"])

    if args.tb:
        pytest_args.extend(["--tb", args.tb])

    # 添加设备序列号参数
    if args.serial:
        pytest_args.extend(["--device-serial", args.serial])
    else:  # 当没有指定设备序列号时，自动获取第一个设备序列号
        device_sn = get_first_sn()
        if not device_sn:
            raise ValueError("未检测到设备序列号，请连接设备或手动指定序列号")
        pytest_args.extend(["--device-serial", device_sn])

    if getattr(args, "reruns", None):
        pytest_args.extend(["--reruns", str(args.reruns)])
    if getattr(args, "reruns_delay", None):
        pytest_args.extend(["--reruns-delay", str(args.reruns_delay)])
    if getattr(args, "skip_spd_info", False):
        pytest_args.append("--skip-spd-info")

    return pytest_args


def run(args=None):
    pytest.main(build_pytest_args(args))


def install_requirements():
    # 检查 requirements.txt 是否存在
    requirements_file = "requirements.txt"
    if not os.path.exists(requirements_file):
        print(f"错误: {requirements_file} 文件不存在！")
        return

    try:
        # 获取已安装的依赖列表
        installed_packages = subprocess.check_output(
            ["pip", "list", "--format=freeze"]
        ).decode("utf-8")
        installed_packages = [
            pkg.split("==")[0].lower() for pkg in installed_packages.splitlines()
        ]

        # 读取 requirements.txt 中的依赖
        import re
        with open(requirements_file, "r", encoding="utf-8") as f:
            required_packages = []
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    # 使用正则提取包名，支持 ==, ~=, >=, <=, >, <
                    match = re.split(r"[=<>~!]", line)
                    if match:
                        required_packages.append(match[0].strip().lower())

        # 筛选未安装的依赖
        missing_packages = [
            pkg for pkg in required_packages if pkg not in installed_packages
        ]

        if missing_packages:
            print(f"正在安装缺失的依赖: {', '.join(missing_packages)}...")
            subprocess.check_call(
                [
                    "pip",
                    "install",
                    "-i",
                    "https://mirrors.aliyun.com/pypi/simple/",
                    "-r",
                    requirements_file,
                ]
            )
            print("依赖安装完成！")
        else:
            print("所有依赖已安装，无需重复安装。")

        # 单独处理 numpy 的预发布版本
        if "numpy" not in installed_packages:
            print("正在安装 numpy 的预发布版本...")
            subprocess.check_call(
                [
                    "pip",
                    "install",
                    "-i",
                    "https://mirrors.aliyun.com/pypi/simple/",
                    "--pre",
                    "numpy",
                ]
            )
            print("numpy 安装完成！")
        else:
            print("numpy 已安装，跳过安装。")
    except subprocess.CalledProcessError as e:
        print(f"安装依赖时出错: {e}")
    except Exception as e:
        print(f"发生未知错误: {e}")


if __name__ == "__main__":
    # install_requirements()
    args = parse_args()
    run(args)
