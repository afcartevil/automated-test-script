import logging
from contextlib import contextmanager


@contextmanager
def log_safety():
    """ 动态修补日志处理机制 """
    original_handlers = {}

    # 定位问题记录器
    target_logger = logging.getLogger("adbutils.shell")

    try:
        # 备份原始处理器
        original_handlers = target_logger.handlers.copy()

        # 定义安全处理器
        class FormatSafeHandler(logging.Handler):
            def emit(self, record):
                try:
                    # 安全格式化检测
                    record.msg % record.args
                except (TypeError, KeyError, ValueError):
                    # 自动修正参数
                    record.args = ()
                finally:
                    # 使用原始处理器输出（保持原有输出逻辑）
                    for handler in original_handlers:
                        handler.emit(record)

        # 清除旧处理器，添加新处理器
        target_logger.handlers = [FormatSafeHandler()]

        # 继续执行测试
        yield

    finally:
        # 恢复原始处理器
        target_logger.handlers = original_handlers
