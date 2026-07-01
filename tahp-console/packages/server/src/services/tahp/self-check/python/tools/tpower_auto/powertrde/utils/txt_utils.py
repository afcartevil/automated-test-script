
def write_to_txt(filename: str, content: str):
    """
    将给定的内容写入到指定的TXT文件中。

    :param filename: 文件名（包括路径）
    :param content: 要写入的内容
    """
    try:
        with open(filename, 'w', encoding='utf-8') as file:
            file.write(content)
    except Exception as e:
        print(f"写入文件时出现错误: {e}")


def read_from_txt(filename: str) -> str:
    """
    从指定的TXT文件中读取内容。

    :param filename: 文件名（包括路径）
    :return: 文件内容
    """
    try:
        with open(filename, 'r', encoding='utf-8') as file:
            content = file.read()
        return content
    except Exception as e:
        print(f"读取文件时出现错误: {e}")
        return ""