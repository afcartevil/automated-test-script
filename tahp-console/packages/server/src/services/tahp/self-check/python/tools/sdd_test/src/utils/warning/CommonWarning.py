# coding=utf-8


class PartitionWarning(Warning):
    """
    分区检查警告基类
    用于表示分区大小检查中发现的非致命问题
    """

    def __init__(self, message=""):
        """
        初始化分区警告
        :param message: 警告描述信息
        """
        self.message = message

    def __str__(self):
        return self.message
