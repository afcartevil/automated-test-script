import os
import logging
import datetime
from threading import Lock

DEFAULT_TAG = "tpytest-ppt"

class Logger:
    _instance = None
    _lock = Lock()

    def __new__(cls, sn=None, base_path=None, cmd_level=logging.INFO, file_level=logging.INFO):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(Logger, cls).__new__(cls)
                cls._instance.initialize(sn, base_path, cmd_level, file_level)
            return cls._instance

    def initialize(self, sn, base_path, cmd_level=logging.INFO, file_level=logging.INFO):
        self.__tag = DEFAULT_TAG
        self.__logger = logging.getLogger()
        self.__logger.setLevel(logging.INFO)
        self.__file_level = file_level
        self.__formatter = logging.Formatter('[%(asctime)s][%(levelname)s] %(message)s', '%Y-%m-%d %H:%M:%S')

        self.__sh = logging.StreamHandler()
        self.__sh.setFormatter(self.__formatter)
        self.__sh.setLevel(cmd_level)

        # Generate log path based on project root, date, and SN
        # project_root = os.path.dirname(os.path.abspath(__file__))
        date_folder = datetime.datetime.now().strftime("%Y-%m-%d")
        log_folder = os.path.join(base_path, date_folder)
        if not os.path.isdir(log_folder):
            os.makedirs(log_folder)

        log_file_path = os.path.join(log_folder, f"{sn}.txt")

        self.__fh = logging.FileHandler(log_file_path, encoding="utf-8")
        self.__fh.setFormatter(self.__formatter)
        self.__fh.setLevel(file_level)

        self.__logger.addHandler(self.__sh)
        self.__logger.addHandler(self.__fh)

    def setDebugMode(self):
        self.__logger.setLevel(logging.DEBUG)
        self.__sh.setLevel(logging.DEBUG)
        self.__fh.setLevel(logging.DEBUG)

    def resetLogFile(self, log_path):
        self.__logger.removeHandler(self.__fh)

        fh = logging.FileHandler(log_path, encoding="utf-8")
        fh.setFormatter(self.__formatter)
        fh.setLevel(self.__file_level)
        self.__logger.addHandler(fh)

    def resetTag(self, tag=None):
        if tag is None:
            self.__tag = DEFAULT_TAG
        else:
            self.__tag = tag

    def debug(self, message, sn=None, tag=None):
        if tag is None:
            tag = self.__tag
        if sn is not None:
            self.__logger.debug("[{}][{}] --- {}".format(tag, sn, message))
        else:
            self.__logger.debug("[{}] --- {}".format(tag, message))

    def info(self, message, sn=None, tag=None):
        if tag is None:
            tag = self.__tag
        if sn is not None:
            self.__logger.info("[{}][{}] --- {}".format(tag, sn, message))
        else:
            self.__logger.info("[{}] --- {}".format(tag, message))

    def warn(self, message, sn=None, tag=None):
        if tag is None:
            tag = self.__tag
        if sn is not None:
            self.__logger.warning("[{}][{}] --- {}".format(tag, sn, message))
        else:
            self.__logger.warning("[{}] --- {}".format(tag, message))

    def error(self, message, sn=None, tag=None):
        if tag is None:
            tag = self.__tag
        if sn is not None:
            self.__logger.error("[{}][{}] --- {}".format(tag, sn, message))
        else:
            self.__logger.error("[{}] --- {}".format(tag, message))

    def critical(self, message, sn=None, tag=None):
        if tag is None:
            tag = self.__tag
        if sn is not None:
            self.__logger.critical("[{}][{}] --- {}".format(tag, sn, message))
        else:
            self.__logger.critical("[{}] --- {}".format(tag, message))





