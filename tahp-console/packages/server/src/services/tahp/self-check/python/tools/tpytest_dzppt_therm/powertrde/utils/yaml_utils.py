import os
from contextlib import contextmanager

import yaml
from ruamel.yaml import YAML, CommentedMap

from powertrde import env
from powertrde.framework.logs_protocol import logs_p
from powertrde.utils import file_utils, confuse_utils


@contextmanager
def _defused_file_open(filepath):
    yield confuse_utils.defuse_string(file_utils.read_all_text(filepath), passphrase=env.TEXT_CONFUSED_KEY)


class NoAliasDumper(yaml.SafeDumper):
    def ignore_aliases(self, data):
        return True


def convert_value(value):
    if isinstance(value, str):
        # 尝试将字符串转换为整数
        if value.isdigit():
            return int(value)
        # 尝试将字符串转换为浮点数
        try:
            return float(value)
        except ValueError:
            pass
        # 如果字符串是布尔值
        if value.lower() in ['true', 'false']:
            return value.lower() == 'true'
        # 保持字符串不变
        return value
    elif isinstance(value, list):
        # 递归转换列表中的每个元素
        return [convert_value(item) for item in value]
    elif isinstance(value, dict):
        # 递归转换字典中的每个值
        return {k: convert_value(v) for k, v in value.items()}
    else:
        # 已经是正确的类型，直接返回
        return value


def read_yaml(file_path, ignore_yaml_error=True):
    """
    读取 YAML 文件并返回数据。

    :param file_path: YAML 文件的路径
    :param ignore_yaml_error: 是否忽略 yaml 错误类型
    :return: YAML 文件中的数据（字典或列表）
    """
    if not os.path.exists(file_path):
        if ignore_yaml_error:
            return None
        else:
            raise FileNotFoundError(f'Cannot find {file_path}.')
    with _defused_file_open(file_path) as file:
        try:
            data = yaml.safe_load(file)
            # if data is not None:
            #     # 递归转换数据结构中的每个值
            #     return convert_value(data)
            return data
        except yaml.YAMLError as exc:
            if ignore_yaml_error:
                logs_p().log(exc)
                return None
            else:
                raise exc


def read_yaml_append_to_dict(file_path, target_dict: dict):
    read_result = read_yaml(file_path, False)
    if read_result:
        if isinstance(read_result, dict):
            target_dict.update(read_result)
        else:
            raise Exception('The read_yaml_append_to_dict method can only read dictionary-type YAML.')


def write_yaml(data, file_path, ignore_yaml_error=True, write_mode='w', no_alias=False, confuse_file=False):
    """
    将数据写入 YAML 文件。

    :param data: 要写入的数据（字典或列表）
    :param ignore_yaml_error: 是否忽略 yaml 错误类型
    :param file_path: YAML 文件的路径
    :param write_mode: 文件写入模式
    :param no_alias: 在yaml文件写入时，是否使用无别名模式（无别名将强制将引用关系拆解为复制体，防止yaml里出现引用符号）
    :param confuse_file: 是否混淆文件（使用env.TEXT_CONFUSED_KEY）
    """
    # data = convert_value(data)
    # 获取文件所在的目录路径
    directory = os.path.dirname(file_path)

    # 如果目录不存在，则创建目录
    if directory and not os.path.exists(directory):
        os.makedirs(directory)

    with open(file_path, write_mode, encoding='utf-8') as file:
        try:
            if no_alias:
                yaml.dump(data, file, Dumper=NoAliasDumper, allow_unicode=True, default_flow_style=False, sort_keys=False)
            else:
                yaml.safe_dump(data, file, allow_unicode=True, default_flow_style=False, sort_keys=False)
        except yaml.YAMLError as exc:
            if ignore_yaml_error:
                logs_p().log(exc)
                return False
            else:
                raise exc
    if confuse_file:
        confuse_utils.confuse_file(file_path, passphrase=env.TEXT_CONFUSED_KEY)
    return True


def write_yaml_in_add(data, file_path, ignore_yaml_error=True, no_alias=False):
    """
    将数据写入 YAML 文件。（追加）

    :param data: 要写入的数据（字典或列表）
    :param ignore_yaml_error: 是否忽略 yaml 错误类型
    :param file_path: YAML 文件的路径
    :param no_alias: 在yaml文件写入时，是否使用无别名模式（无别名将强制将引用关系拆解为复制体，防止yaml里出现引用符号）
    """
    return write_yaml(data, file_path, ignore_yaml_error, 'a', no_alias=no_alias)


def read_yaml_retain_annotations(file_path):
    """读取 YAML 文件并返回数据"""
    _yaml = YAML()
    _yaml.preserve_quotes = True  # 保留引号和注释

    with _defused_file_open(file_path) as file:
        _data = _yaml.load(file)

    return _data


def modify_yaml_data(data, key_to_modify, new_value):
    """修改 YAML 数据字典中的指定键的值"""
    if key_to_modify in data:
        data[key_to_modify] = new_value
        print(f"已更新 '{key_to_modify}' 的值为: {new_value}")
    else:
        print(f"键 '{key_to_modify}' 不存在于数据中。")
    return data


def write_yaml_retain_annotations(data, file_path):
    """将数据写回 YAML 文件"""
    _yaml = YAML()
    _yaml.preserve_quotes = True  # 保留引号和注释

    with open(file_path, 'w', encoding='utf-8') as file:
        _yaml.dump(data, file)
        # print(f"文件已更新并写入: {file_path}")


def merge_yaml_and_save(a_file_path: str, b_file_path: str, output_file_path: str):
    _yaml = YAML()
    _yaml.preserve_quotes = True  # 保留引号
    _yaml.indent(mapping=2, sequence=4, offset=2)  # 设置缩进

    # 读取a.yaml文件
    with open(a_file_path, 'r', encoding='utf-8') as a_file:
        a_data = _yaml.load(a_file)

    # 读取b.yaml文件
    with open(b_file_path, 'r', encoding='utf-8') as b_file:
        b_data = _yaml.load(b_file)

    # 检查并合并b_dict中的键值对和注释到a_dict
    modified = False
    if isinstance(a_data, CommentedMap) and isinstance(b_data, CommentedMap):
        for key in b_data:
            if key not in a_data:
                a_data[key] = b_data[key]
                # 复制注释
                if b_data.ca.items.get(key):
                    a_data.ca.items[key] = b_data.ca.items[key]
                modified = True

        # 合并文件级别的注释
        if b_data.ca.comment and not a_data.ca.comment:
            a_data.ca.comment = b_data.ca.comment
            modified = True

        # 检查首个字段的注释
        for key in a_data:
            if b_data.ca.items.get(key) and not a_data.ca.items.get(key):
                a_data.ca.items[key] = b_data.ca.items[key]

    # 仅当字典被修改时写回合并后的数据
    if modified:
        with open(output_file_path, 'w', encoding='utf-8') as output_file:
            _yaml.dump(a_data, output_file)


# 示例用法
if __name__ == "__main__":
    ...
    # 读取 YAML 文件
    # data = read_yaml_retain_annotations(r'D:\Projects\dz_auto_env\tpytest_dzppt_perf\config\dzppt\perf\base_config.yaml')
    # print(data)
    # _pretest_level = data['pretest_level']
    # _whole_test = data['is_whole_device_test']
    # modify_yaml_data(data, "pretest_level", 5)
    # print(_pretest_level)
    # write_yaml_retain_annotations(data, 'hhh.yaml')
    # source_file = os.path.join(r'D:\RUN\ppt\dz_auto_env\config\dzppt', "dou3", "base_config.yaml")
    # print(os.path.exists(source_file))
    # merge_yaml_and_save(r'D:\dz_auto_env_configs\dou3_user_config.yaml', source_file,
    #                     r'D:\dz_auto_env_configs\dou3_user_config.yaml')
