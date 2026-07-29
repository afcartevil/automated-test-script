from typing import Union


class CaseDataAssertionError(AssertionError):
    """自定义用例数据异常类，用于断言用例数据收集成功但不符合业务目标时抛出"""

    def __init__(self, message, expression):
        super().__init__(f"{message}. Expression: {expression}")


class CombinedTestException(Exception):
    def __init__(self, exceptions: list):
        """
        接受多个 Exception 实例，并存储在 self.exceptions 中。
        """
        self.exceptions = exceptions
        summary = "; ".join(f"{type(e).__name__}: {e!s}"
                            for e in self.exceptions)
        super().__init__(f"CombinedTestException: [{summary}]")

    def has_exception_type(self, exception_type: Union[type, tuple]):
        """
        检查 self.exceptions 中是否包含指定类型的异常。

        参数:
            exception_type: 单个异常类型或一个包含多个异常类型的元组。

        返回:
            bool: 如果 self.exceptions 中存在指定类型的异常，则返回 True，否则返回 False。
        """
        return any(isinstance(e, exception_type) for e in self.exceptions)

    # def __repr__(self):
    #     """
    #     repr(obj) 时调用，展示简要汇总信息：
    #     CombinedTestException[Type1: msg1; Type2: msg2; ...]
    #     """
    #     summary = "; ".join(f"{type(e).__name__}: {e!s}"
    #                         for e in self.exceptions)
    #     return f"CombinedTestException: [{summary}]"
    #
    # def __str__(self):
    #     """
    #     str(obj) 或 print(obj) 时调用，展示每个异常的完整 traceback。
    #     """
    #     parts = []
    #     for idx, exc in enumerate(self.exceptions, 1):
    #         tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    #         parts.append(f"----- The traceback of exception {idx} -----\n{tb}")
    #     return "\n".join(parts)

