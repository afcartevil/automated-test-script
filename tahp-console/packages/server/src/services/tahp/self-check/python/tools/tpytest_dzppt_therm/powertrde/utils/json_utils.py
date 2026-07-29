import json
import subprocess
from typing import Any, Dict, Optional
import os

# class JsonUtil:
#     @staticmethod
def read_json_file(file_path: str) -> Any:
    """
    读取 JSON 文件并返回其内容。

    :param file_path: JSON 文件路径
    :return: 解析后的 JSON 数据
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            data = json.load(file)
        return data
    except FileNotFoundError:
        print(f"File {file_path} not found")
    except json.JSONDecodeError:
        print(f"File {file_path} is not a valid JSON")
    except Exception as e:
        print(f"An error occurred while reading the file {file_path}: {e}")


def write_json_file(file_path: str, data: Any, indent: Optional[int] = 4) -> None:
    """
    将数据写入 JSON 文件。

    :param file_path: JSON 文件路径
    :param data: 要写入的数据
    :param indent: 缩进级别
    """
    try:
        with open(file_path, 'w', encoding='utf-8') as file:
            json.dump(data, file, ensure_ascii=False, indent=indent)
        print(f"Data has been successfully written to {file_path}")
    except Exception as e:
        print(f"An error occurred while writing to the file {file_path}: {e}")


def read_json_string(json_string: str) -> Any:
    """
    解析 JSON 字符串并返回其内容。

    :param json_string: JSON 字符串
    :return: 解析后的 JSON 数据
    """
    try:
        data = json.loads(json_string)
        return data
    except json.JSONDecodeError:
        print("The provided string is not a valid JSON")
    except Exception as e:
        print(f"An error occurred while parsing the JSON string: {e}")


def write_json_string(data: Any, indent: int = 4) -> str:
    """
    将数据转换为 JSON 字符串。

    :param data: 要转换的数据
    :param indent: 缩进级别
    :return: JSON 字符串
    """
    try:
        json_string = json.dumps(data, ensure_ascii=False, indent=indent)
        return json_string
    except Exception as e:
        print(f"An error occurred while converting to a JSON string: {e}")
        return ""

def read_android_json(path):
    try:
        # 调用 adb shell cat 读取文件
        result = subprocess.run(
            ["adb", "shell", "cat", path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        # 如果 adb 命令失败，直接返回 None
        if result.returncode != 0:
            print(f"读取失败: {result.stderr.decode('utf-8', errors='ignore').strip()}")
            return None

        # 转为字符串
        content = result.stdout.decode("utf-8", errors="ignore").strip()
        if not content:
            print("文件为空或不存在")
            return None

        # 尝试解析 JSON
        try:
            data = json.loads(content)
            return data
        except json.JSONDecodeError:
            print("JSON 解析失败，原始内容：")
            print(content)
            return None

    except Exception as e:
        print(f"异常: {e}")
        return None


def write_android_json(data, remote_path):
    """
    将 Python 数据写入 Android 设备上的 JSON 文件

    :param data: dict / list，可以转成 JSON 的对象
    :param remote_path: Android 设备上的目标路径
    :return: True 成功, False 失败
    """
    try:
        # 用户目录
        user_dir = os.path.expanduser("~")

        # 直接取远端文件名（保持一致，不拼接后缀）
        base_name = os.path.basename(remote_path)
        local_file = os.path.join(user_dir, base_name)

        # 写入 JSON
        with open(local_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        # adb push
        result = subprocess.run(
            ["adb", "push", local_file, remote_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        if result.returncode != 0:
            print(f"写入失败: {result.stderr.decode('utf-8', errors='ignore').strip()}")
            return False

        print(f"成功写入 {remote_path} (本地文件: {local_file})")
        return True

    except Exception as e:
        print(f"异常: {e}")
        return False


# 示例用法
# if __name__ == "__main__":
#     json_util = JsonUtil()
#
#     # 写入 JSON 文件
#     data_to_write = {"name": "Alice", "age": 30, "city": "New York"}
#     json_util.write_json_file("example.json", data_to_write)
#
#     # 读取 JSON 文件
#     data_read = json_util.read_json_file("example.json")
#     print(data_read)
#
#     # 写入 JSON 字符串
#     json_string = json_util.write_json_string(data_to_write)
#     print(json_string)
#
#     # 读取 JSON 字符串
#     data_from_string = json_util.read_json_string(json_string)
#     print(data_from_string)
