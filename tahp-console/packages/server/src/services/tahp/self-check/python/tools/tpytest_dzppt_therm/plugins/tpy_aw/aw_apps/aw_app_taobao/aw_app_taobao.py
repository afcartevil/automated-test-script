import time

from tpy_aw import U2WatchersCommon
from tpy_aw.aw_app_base import AwAppBase
from tpy_aw.aw_apps.aw_app_snapchat.u2_watchers_snapchat import U2WatchersSnapchat


class AwAppTaobao(AwAppBase):
    aw_name = 'Taobao'
    default_app_package = 'com.taobao.taobao'
