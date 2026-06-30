import logging
import tomllib


def read_toml(toml_file, key_path=None):
    """读取TOML配置文件，支持通过key_path获取指定路径的值。

    Args:
        toml_file: TOML文件路径。
        key_path: 用"."分隔的键路径，为None时返回整个文件的字典。

    Returns:
        对应路径的值，路径不存在时返回None。

    Examples:
        >>> read_toml("pyproject.toml")
        {"tool": {"black": {"line-length": 88}, "my_app": {"credentials": {"username": "admin"}}}}

        >>> read_toml("pyproject.toml", "tool.my_app.credentials")
        {"username": "admin", "password": "123456"}

        >>> read_toml("pyproject.toml", "tool.my_app.credentials.username")
        "admin"

        >>> read_toml("pyproject.toml", "tool.my_app.not_exist")
        None
    """
    try:
        with open(toml_file, "rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError:
        logging.warning(f"File '{toml_file}' not found.")
        return None
    except tomllib.TOMLDecodeError as e:
        logging.warning(f"Failed to parse toml file '{toml_file}': {e}")
        return None

    if key_path is None:
        return data

    keys = key_path.split(".")
    result = data
    for key in keys:
        if not isinstance(result, dict) or key not in result:
            logging.warning(f"Key path '{key_path}' not found in '{toml_file}'.")
            return None
        result = result[key]
    return result
