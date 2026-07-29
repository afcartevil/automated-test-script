import time

from uiautomator2 import XPathElementNotFoundError

from powertrde.framework.tran_logger import t_log
from powertrde.utils.u2_extends.u2_selector import U2Selector
from tpy_aw.aw_apps.aw_app_aigallery.aw_app_aigallery_xiaomi import AwAppAiGalleryXiaomi
from tpy_aw.aw_apps.aw_app_phone.aw_app_phone_xiaomi import PhoneXiaomiLocator, AwAppPhoneXiaomi


class AwAppAiGalleryXiaomiHyperR(AwAppAiGalleryXiaomi):
    aw_nickname = "XiaomiRGallery"
    variant_key = 'xiaomi_hyper_r'
    default_app_package = 'com.miui.gallery'

    ...