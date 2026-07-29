from powertrde.utils.u2_extends.u2_selector import U2Selector
from tpy_aw.aw_apps.aw_app_phone.aw_app_phone_xiaomi import PhoneXiaomiLocator, AwAppPhoneXiaomi


class PhoneXiaomiHyperRLocator(PhoneXiaomiLocator):
    btn_go_to_settings = U2Selector().xpath('//android.widget.TextView[@text="Go to Settings"]').bind()
    btn_param_text = U2Selector().xpath_text('{param_text}').bind()
    number_one_button = U2Selector().xpath('//*[@text="1"]').bind()


class AwAppPhoneXiaomiHyperR(PhoneXiaomiHyperRLocator, AwAppPhoneXiaomi):
    aw_nickname = "XiaomiRPhone"
    variant_key = 'xiaomi_hyper_r'
    default_app_package = 'com.android.contacts'

    ...
