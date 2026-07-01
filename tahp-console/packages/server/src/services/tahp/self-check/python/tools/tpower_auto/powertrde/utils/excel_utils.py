from dataclasses import dataclass

from typing import Dict, Any, Optional
from openpyxl import Workbook
from openpyxl.reader.excel import load_workbook
from openpyxl.utils import get_column_letter
from openpyxl.styles import Alignment, PatternFill, Font, Border, Side
from openpyxl.cell import Cell
from openpyxl.worksheet.worksheet import Worksheet


def find_cell_in_row(sheet: Worksheet, row_number: int, target_value, start_col=1, end_col=-1) -> Optional[Cell]:
    # 获取该行的最大列数
    max_col = sheet.max_column

    # 如果结束列为负数，或者大于最大列数，则设置为最大列数
    if end_col <= 0 or end_col > max_col:
        end_col = max_col

    # 遍历指定范围的列
    for col in range(start_col, end_col + 1):
        cell = sheet.cell(row=row_number, column=col)
        if cell.value == target_value:
            return cell

    return None


def find_cell_in_col(sheet: Worksheet, col_number: int, target_value, start_row=1, end_row=-1) -> Optional[Cell]:
    # 获取该列的最大行数
    max_row = sheet.max_row

    # 如果结束行为负数，或者大于最大行数，则设置为最大行数
    if end_row <= 0 or end_row > max_row:
        end_row = max_row

    # 遍历指定范围的行
    for row in range(start_row, end_row + 1):
        cell = sheet.cell(row=row, column=col_number)
        if cell.value == target_value:
            return cell
    return None


def get_key_cells_dict_in_row(sheet: Worksheet, row_number: int, start_col=1, end_col=-1) -> Dict[Any, Cell]:
    # 获取该行的最大列数
    max_col = sheet.max_column

    # 如果结束列为负数，或者大于最大列数，则设置为最大列数
    if end_col <= 0 or end_col > max_col:
        end_col = max_col

    result_dict = {}

    # 遍历指定范围的列
    for col in range(start_col, end_col + 1):
        cell = sheet.cell(row=row_number, column=col)
        cell_value = cell.value
        if cell_value is None or cell_value == "":
            continue  # 跳过空值单元格
        if cell_value in result_dict:
            raise Exception(f'Duplicate key found: {cell_value}')
        result_dict[cell_value] = cell

    return result_dict


def get_key_cells_dict_in_col(sheet: Worksheet, col_number: int, start_row=1, end_row=-1) -> Dict[Any, Cell]:
    # 获取该列的最大行数
    max_row = sheet.max_row

    # 如果结束行为负数，或者大于最大行数，则设置为最大行数
    if end_row <= 0 or end_row > max_row:
        end_row = max_row

    result_dict = {}

    # 遍历指定范围的行
    for row in range(start_row, end_row + 1):
        cell = sheet.cell(row=row, column=col_number)
        cell_value = cell.value
        if cell_value is None or cell_value == "":
            continue  # 跳过空值单元格
        if cell_value in result_dict:
            raise Exception(f'Duplicate key found: {cell_value}')
        result_dict[cell_value] = cell

    return result_dict


def get_one_row_cells_by_header_dict(sheet: Worksheet, value_row_number: int, row_key_cells_dict: Dict[Any, Cell]) -> \
        Dict[Any, Cell]:
    result_dict = {}
    for key, cell in row_key_cells_dict.items():
        result_dict[key] = sheet.cell(row=value_row_number, column=cell.column)
    return result_dict


def get_one_col_cells_by_header_dict(sheet: Worksheet, value_col_number: int, col_key_cells_dict: Dict[Any, Cell]) -> \
        Dict[Any, Cell]:
    result_dict = {}
    for key, cell in col_key_cells_dict.items():
        result_dict[key] = sheet.cell(row=cell.row, column=value_col_number)
    return result_dict


def iterate_col_cells_until_empty_cell(sheet: Worksheet, column: int, row_start: int):
    while True:
        cell = sheet.cell(row=row_start, column=column)
        cell_value = cell.value
        if cell_value is None or cell_value == "":
            break
        yield cell
        row_start += 1


def iterate_row_cells_until_empty_cell(sheet: Worksheet, row: int, col_start: int):
    while True:
        cell = sheet.cell(row=row, column=col_start)
        cell_value = cell.value
        if cell_value is None or cell_value == "":
            break
        yield cell
        col_start += 1


def read_xls_columns(file_path, columns):
    """
    读取指定的Excel文件（.xls格式）和列，并返回一个字典，其中键是列名，值是列内容的列表。
    :param file_path: Excel文件的路径
    :param columns: 需要读取的列名列表
    :return: 包含指定列的字典:{'总丢帧数': ['12'], '解析失败原因': ['None']}
    """
    import xlrd
    # 打开工作簿
    workbook = xlrd.open_workbook(file_path)
    # 默认读取第一个工作表
    sheet = workbook.sheet_by_index(0)

    # 获取工作表的所有列标题
    headers = sheet.row_values(0)

    # 初始化结果字典
    result = {column: [] for column in columns}

    # 创建一个列名到列索引的映射字典
    column_index_map = {header: index for index, header in enumerate(headers)}

    # 检查指定的列是否在工作表中
    for column in columns:
        if column not in column_index_map:
            print(f"Warning: Column '{column}' not found in the Excel file.")
            continue

    # 遍历工作表的每一行，从第二行开始（数据行）
    for row_idx in range(1, sheet.nrows):
        row = sheet.row_values(row_idx)
        for column in columns:
            if column in column_index_map:
                # 根据列名获取列索引
                column_index = column_index_map[column]
                # 将对应列的值添加到结果字典
                result[column].append(row[column_index])

    return result

def read_xlsx_rows(file_path, sheet_index=0, start_row=3, start_col=2):
    """
    读取指定的Excel文件（.xlsx格式）的所有行数据，并返回一个字典列表，每个字典代表一行数据。
    :param file_path: Excel文件的路径
    :param sheet_index: 需要读取的sheet页索引，默认为0（第一个sheet页）
    :param start_row: 开始读取的行号，默认为3（第一行为标题,第二行为类型,第三行为注释）
    :param start_col: 开始读取的列号，默认为1（第一列）
    :return: 包含所有行数据的字典列表，例如：[{'列名1': '值1', '列名2': '值2'}, {'列名1': '值3', '列名2': '值4'}]
    """
    from openpyxl import load_workbook
    
    # 打开工作簿
    workbook = load_workbook(file_path)
    # 读取指定的工作表
    sheet = workbook.worksheets[sheet_index]

    # 获取工作表的列标题，从start_col开始，并过滤掉空标题的列
    all_headers = sheet[1]  # 第一行的所有单元格
    headers = []  # 存储非空标题
    header_columns = []  # 存储非空标题对应的列号
    
    for col_idx, cell in enumerate(all_headers):
        # 只处理从start_col开始的列
        if col_idx + 1 >= start_col and cell.value is not None and cell.value != "":
            headers.append(cell.value)
            header_columns.append(col_idx + 1)  # openpyxl的列号从1开始

    # 初始化结果列表
    result = []

    # 遍历工作表的每一行，从start_row+1开始（数据行）
    for row in sheet.iter_rows(min_row=start_row+1, values_only=True):
        # 创建一个字典来存储当前行的数据
        row_dict = {}
        for header, col_idx in zip(headers, header_columns):
            # 将每个列名和对应的值添加到行字典中
            row_dict[header] = row[col_idx - 1] if col_idx - 1 < len(row) else None  # openpyxl的行索引从0开始
        # 将当前行字典添加到结果列表中
        result.append(row_dict)

    return result

def gen_excel_util(data, excel_path, sheet_name="testReport", is_center=False):
    """
    规定title信息必须为元组的格式，并且包含列宽的内容，具体格式如下
    """
    # 创建工作簿和工作表
    try:
        workbook = load_workbook(excel_path)
        # 如果工作表存在，删除它
        if sheet_name in workbook.sheetnames:
            del workbook[sheet_name]
    except FileNotFoundError:
        workbook = Workbook()
        # 删除默认创建的工作表
        default_sheet = workbook.active
        workbook.remove(default_sheet)

    worksheet = workbook.create_sheet(title=sheet_name)
    data_title = None
    for item in data:
        # 兼容3种格式，一种是纯字符串的，占所有的列，一种是字典的指定好，一种是list的，按照第一行的顺序进行排
        if isinstance(item, tuple):
            data_title = item
    if not data_title:
        raise Exception("生成excel中的数据没有title信息")
    # 定义列标题和宽度
    columns = [i[0] for i in data_title]  # ['name', 'desc', 'result', 'data', 'endtime']
    column_widths = [i[1] for i in data_title]  # [40, 50, 10, 70, 25]

    # 设置标题行的背景颜色为浅绿色，并加粗，居中
    header_fill = PatternFill(start_color='CCFFCC', end_color='CCFFCC', fill_type='solid')
    header_font = Font(name='微软雅黑', bold=True)
    header_alignment = Alignment(horizontal='center', vertical='center')

    # 定义边框样式
    thin_border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )

    # 写入列标题并设置样式
    for col_num, (column_name, width) in enumerate(zip(columns, column_widths), 1):
        cell = worksheet.cell(row=1, column=col_num, value=column_name)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment
        cell.border = thin_border
        worksheet.column_dimensions[get_column_letter(col_num)].width = width

    # 设置标题行高度为原来的1.5倍
    default_row_height = worksheet.row_dimensions[1].height or 15  # 默认行高是15
    worksheet.row_dimensions[1].height = default_row_height * 1.5

    # 从第二行开始写入数据
    row = 2
    for item in data:
        # 兼容3种格式，一种是纯字符串的，占所有的列，一种是字典的指定好，一种是list的，按照第一行的顺序进行排
        if isinstance(item, str):
            # 合并所有列，并写入字符串
            worksheet.merge_cells(start_row=row, start_column=1, end_row=row, end_column=len(columns))
            cell = worksheet.cell(row=row, column=1, value=item)
            cell.number_format = '@'
            # 设置行高，考虑换行符数量
            line_count = item.count('\n') + 1
            worksheet.row_dimensions[row].height = 15 * line_count
            cell.alignment = Alignment(wrap_text=True, vertical='top')
            # 移动到下一行
            row += 1
        elif isinstance(item, dict):
            # 将字典中的值写入相应的列
            for col_num, column_name in enumerate(columns, 1):
                value = item.get(column_name, '')
                if isinstance(value, dict):
                    value = str(value)
                if isinstance(value, ExcelHyperLinkValue):
                    cell = worksheet.cell(row=row, column=col_num, value=value.value)
                    cell.hyperlink = value.link
                    cell.style = "Hyperlink"  # 设置超链接样式
                else:
                    cell = worksheet.cell(row=row, column=col_num, value=value)
                if isinstance(value, str):
                    cell.number_format = '@'
                if is_center:
                    cell.alignment = Alignment(wrap_text=True, horizontal='center', vertical='center')  # 居中
            # 移动到下一行
            row += 1
        elif isinstance(item, list):
            # 将字典中的值写入相应的列
            for col_num, value in enumerate(item, 1):
                if isinstance(value, (dict, list, int)):
                    value = str(value)
                if isinstance(value, ExcelHyperLinkValue):
                    cell = worksheet.cell(row=row, column=col_num, value=value.value)
                    cell.hyperlink = value.link
                    cell.style = "Hyperlink"  # 设置超链接样式
                else:
                    cell = worksheet.cell(row=row, column=col_num, value=value)
                if isinstance(value, str):
                    cell.number_format = '@'
                if is_center:
                    cell.alignment = Alignment(wrap_text=True, horizontal='center', vertical='center')  # 居中
            # 移动到下一行
            row += 1
    # 保存Excel文件
    workbook.save(excel_path)


def is_merged_cell(sheet: Worksheet, cell: Cell):
    """
    判断单元格是否属于合并单元格范围。
    :param sheet: 工作表对象
    :param cell: 单元格对象 (sheet.cell(row, column))
    :return: 如果属于合并范围返回 True，否则返回 False
    """
    for merged_range in sheet.merged_cells.ranges:
        if cell.coordinate in merged_range:
            return True
    return False


def is_top_left_of_merged_cell_or_single_cell(sheet: Worksheet, cell: Cell):
    """
    检查指定单元格是否为合并单元格的左上角或者只是一个普通单元格。
    :param sheet: 工作表对象
    :param cell: 单元格对象
    :return: 如果是左上角返回 True，否则返回 False
    """
    cell_address = cell.coordinate
    for merged_range in sheet.merged_cells.ranges:
        if cell_address in merged_range:
            # 检查是否是左上角单元格
            min_col, min_row, _, _ = merged_range.bounds
            if cell.row == min_row and cell.column == min_col:
                return True
            else:
                return False
    return True


@dataclass
class ExcelHyperLinkValue:
    value: Any = None
    link: str = None

# if __name__ == '__main__':
#     file_path = "D:\RUN\\ppt\\tpytest-ppt\\.runtime\\20241125_175820三次，没有丢帧\\trace_11442253BF001422\\7下拉通知中心\\trace_analyse_result.xls"
#     columns = ['SF总丢帧数', '滑动总丢帧数']
#     result_dict = read_xls_columns(file_path, columns)
#     print(result_dict)