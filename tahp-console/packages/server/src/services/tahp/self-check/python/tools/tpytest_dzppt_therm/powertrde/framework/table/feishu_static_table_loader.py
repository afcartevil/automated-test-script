import os.path
from typing import List

from powertrde.utils.feishu.feishu_api_helper import FeishuApiHelper
from powertrde.framework.decorators import overwrite
from powertrde.framework.table.base_table_loader import BaseTableLoader
from powertrde.framework.table.default_static_table_loader import DefaultStaticTableLoader


class FeishuStaticTableLoader(BaseTableLoader):
    def __init__(self, feishu_ins: FeishuApiHelper):
        super().__init__()
        self.feishu_instance = feishu_ins

    def _filter_table_name(self, ori_table_name: str):
        """飞书表格不支持二级以上路径，故将表格路径扁平化，仅保留最后一层名称并去掉后缀名，如dou3/table_mock.xlsx会变为dou3和table_mock"""
        # 使用 os.path.basename 获取文件的基本名称（包含后缀）
        base_name_with_extension = os.path.basename(ori_table_name)
        # 使用 os.path.splitext 分离文件名和扩展名
        base_name, _ = os.path.splitext(base_name_with_extension)
        dir_name = os.path.dirname(ori_table_name).replace('\\', '/')
        return dir_name, base_name

    @overwrite
    def on_load_table(self, table_name: str, primary_key_to_lower=False) -> dict:
        table_group, table_name = self._filter_table_name(table_name)
        table_group_token = self.feishu_instance.get_table_group_token(table_group)
        if not table_group_token:
            raise Exception(f"Can not get table group token for '{table_group}', you must use feishu instance to register table token for '{table_group}' first!")
        try:
            sheet_token = self.feishu_instance.get_table_token_by_name(table_group_token, table_name)
            data = self.feishu_instance.read_sheet_data(table_group_token, sheet_token)
            # print(data)
            if data:
                return FeishuStaticTableLoader.list_table_to_dict(data, primary_key_to_lower)
        except Exception as e:
            raise ValueError(f'Can not load {table_name}: ' + str(e))

    @staticmethod
    def list_table_to_dict(data: List[List], primary_key_to_lower=False) -> dict:
        """
        将飞书二维表格数据转换为字典形式。
        参数:
        - data: 飞书读取到的二维数组数据
        - primary_key_to_lower: 是否将主键转为小写
        返回:
        - dict，结构为 {主键: 对应的行数据字典}
        """

        ret_dict = {}
        table_heads = {}
        available_columns = []

        header_row = data[0]  # META
        type_row = data[1]  # TYPE
        data_rows = data[3:]

        for col_index in range(1, len(type_row)):  # 从 index=1 开始，跳过 Meta
            value_type = type_row[col_index]
            if value_type in ["str", "int", "float", "bool", "list", "dict", "json", "/"]:
                if value_type != "/":
                    available_columns.append((col_index, value_type))
            elif value_type is None or value_type == "":
                break
            else:
                raise ValueError(f"Unsupported value type: {value_type} at column {col_index}")

        for col_index, _ in available_columns:
            head_str = header_row[col_index]
            if head_str is None or head_str == "":
                raise ValueError(f"Empty header at column {col_index}")
            table_heads[col_index] = head_str

        for i, row in enumerate(data_rows):
            if len(row) < 2 or not row[1]:
                continue

            row_key = row[1]
            if primary_key_to_lower:
                row_key = row_key.lower()

            sub_dict = {
                "_i": len(ret_dict),
                "_ori_id": row[1]
            }

            for col_index, value_type in available_columns:
                cell_value = row[col_index] if col_index < len(row) else None
                converted_value = DefaultStaticTableLoader.convert_table_value(cell_value, value_type)
                if col_index == 1 and primary_key_to_lower:
                    converted_value = converted_value.lower()
                sub_dict[table_heads[col_index]] = converted_value

            ret_dict[row_key] = sub_dict

        return ret_dict


if __name__ == "__main__":
    # DOU3.0自动化表格
    # https://transsioner.feishu.cn/sheets/STlAs1HDZhqLG4tMB4xcIrtunSb?sheet=785c48
    dou3_app_id = 'cli_a88b4d15dc70100b'
    dou3_app_secret = 'nTOW0ZolI9RssVN8gact5eVcLVtljJC2'
    dou3_table_token = 'STlAs1HDZhqLG4tMB4xcIrtunSb'
    _feishu_ins = FeishuApiHelper(dou3_app_id, dou3_app_secret)
    _feishu_ins.register_table_group_token('dou3', dou3_table_token)
    loader = FeishuStaticTableLoader(_feishu_ins)
    print(loader.load_table('dou3/table_dou3_products'))
