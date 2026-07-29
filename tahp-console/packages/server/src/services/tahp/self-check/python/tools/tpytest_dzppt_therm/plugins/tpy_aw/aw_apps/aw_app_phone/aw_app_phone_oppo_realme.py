from tpy_aw.aw_apps.aw_app_phone.aw_app_phone import AwAppPhone
from tpy_aw.aw_apps.aw_app_phone.aw_app_phone_oppo import AwAppPhoneOppo


class AwAppPhoneOppoRealme(AwAppPhoneOppo):
    variant_key = 'oppo_realmeui'
    default_app_package = 'com.google.android.dialer'


