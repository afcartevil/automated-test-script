from powertrde.framework.tran_logger.tran_logger import TranLogger

_logger_name = None

_specific_logger = None


def get_logger(name: str, auto_create: bool = False):
    return TranLogger.get_logger(name, auto_create=auto_create)


def set_default_logger(_logger: TranLogger):
    TranLogger.set_default(_logger)


def switch_logger_by_name(logger_name: str):
    global _logger_name, _specific_logger
    _logger_name = logger_name
    _specific_logger = None


def switch_logger(specific_logger: TranLogger):
    global _logger_name, _specific_logger
    _logger_name = None
    _specific_logger = specific_logger


def logger():
    if _specific_logger is not None:
        return _specific_logger
    return TranLogger.get_logger(_logger_name)


def debug(msg: str, *args, **kwargs):
    logger().debug(msg, *args, **kwargs)


def info(msg: str, *args, **kwargs):
    logger().info(msg, *args, **kwargs)


def warning(msg: str, *args, **kwargs):
    logger().warning(msg, *args, **kwargs)


def error(msg: str, *args, **kwargs):
    logger().error(msg, *args, **kwargs)


def error_with_tag(msg: str, error_tag='error', *args, **kwargs):
    """记录 error 级别日志，并且自动将额外的error_tag带入tag中"""
    logger().error_with_tag(msg, error_tag, *args, **kwargs)


def exception(msg: str, *args, exc_info=True, **kwargs):
    logger().exception(msg, *args, exc_info, **kwargs)
