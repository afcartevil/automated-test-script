from datetime import datetime

def parse_iso_format(date_string, delete_second=True):
    # 如果小数部分不足三位，则补齐,东舟机械手容易生成这种时间,需要兼容一下
    """
    兼容类似的时间:date_str2 = "2025-03-21T18:05:41.1"
    """
    if '.' in date_string:
        if delete_second:
            # 只保留到秒的部分
            date_string = date_string.split('.')[0]
        else:
            date_part, fraction = date_string.split('.')
            fraction = fraction.ljust(3, '0')  # 补齐到三位
            date_string = f"{date_part}.{fraction}"

    return datetime.fromisoformat(date_string)
