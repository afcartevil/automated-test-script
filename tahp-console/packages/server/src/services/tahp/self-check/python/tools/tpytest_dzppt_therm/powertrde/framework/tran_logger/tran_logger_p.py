from powertrde.framework.tran_logger.tran_logger import TranLogger


class TranLoggerP:
    def __init__(self, tran_logger: TranLogger):
        self.tran_logger = tran_logger

    def log_error(self, info, device_id='', exc_info=None):
        self.tran_logger.error(info, tag=device_id, exc_info=exc_info)

    def log(self, info, device_id=''):
        self.tran_logger.info(info, tag=device_id)

    def log_exception(self, exception, device_id='', exc_info=True):
        self.tran_logger.exception(exception, tag=device_id)

    def log_debug(self, info, device_id=''):
        self.tran_logger.debug(info, tag=device_id)

    def log_warning(self, info, device_id=''):
        self.tran_logger.warning(info, tag=device_id)

    def get_log_dir(self) -> str:
        return self.tran_logger.log_dir
