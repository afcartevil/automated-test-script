import os
from os import path


def path_join(path1, path2):
    # 判断平台类型，如果是Windows系统，使用os.path.join函数拼接路径；否则使用'/'作为分隔符拼接路径。
    # if os.name == 'nt':
    #     return os.path.join(path1, path2)
    # else:
    return path1 + "/" + path2 if path1[-1] != "/" else path1 + path2
