import os
import time
from typing import Optional


class DzApiError(Exception):
    """东舟API基础异常"""

    def __init__(self, msg: str, error_code: Optional[int] = None):
        self.error_code = error_code
        super().__init__(f"[DZ-ERR{error_code or ''}] {msg}")


class OperationFailed(DzApiError):
    """操作执行失败"""


class TestExecutionError(DzApiError):
    """测试用例执行异常"""


class TestExecutionFailed(DzApiError):
    """测试用例执行失败"""

    def __init__(self, msg: str, response: dict, error_code: Optional[int] = None):
        super().__init__(msg, error_code)
        self.response: dict = response

    @property
    def summary(self) -> str:
        """Extracts the last 10 lines from the log.txt in the specified WorkFolder."""
        if not self.response or 'WorkFolder' not in self.response:
            return "No summary available."

        work_folder = self.response['WorkFolder']
        log_file_path = os.path.join(work_folder, "log.txt")

        try:
            with open(log_file_path, 'r', encoding='utf-8') as log_file:
                lines = log_file.readlines()
                last_lines = lines[-10:] if len(lines) >= 10 else lines
                return ''.join(last_lines)
        except (FileNotFoundError, IOError):
            return "Log file not found or cannot be read."

    def __str__(self):
        response_info = f"\nResponse: {self.response}" if self.response else ""
        summary_info = f"\nSummary:\n{self.summary}"
        return f"{super().__str__()}{response_info}{summary_info}"


def dz_retry(retries=3, delay=1):
    """重试装饰器"""

    def decorator(func):
        def wrapper(*args, **kwargs):
            for i in range(retries):
                try:
                    return func(*args, **kwargs)
                except DzApiError as e:
                    if i == retries - 1:
                        raise
                    time.sleep(delay)
                    continue
            return func(*args, **kwargs)

        return wrapper

    return decorator
