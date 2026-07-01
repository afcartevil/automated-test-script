import time

from powertrde.framework.tran_logger import t_log
from powertrde.utils.trde import adb
from tpy_aw.aw_app_base import AwAppBase


class AwAppMobileLegends(AwAppBase):
    aw_name = 'MobileLegends'
    default_app_package = 'com.mobile.legends'
