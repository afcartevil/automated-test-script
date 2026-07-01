import json
from typing import Any, Dict, Optional


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
