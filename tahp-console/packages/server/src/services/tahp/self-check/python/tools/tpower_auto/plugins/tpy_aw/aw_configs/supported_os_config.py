from enum import Enum

from tpy_aw.aw_defines import PhoneOsInfo


class SupportedOS(Enum):
    UNKNOWN = PhoneOsInfo(key='UNKNOWN', vendor_name='', os_name='unknown', props_keyword='[unknown os]', launcher='com.android.launcher3')
    TRAN_HIOS = PhoneOsInfo(key='TRAN_HIOS', vendor_name='transsion', os_name='hios', props_keyword='[hios]', launcher='com.transsion.hilauncher')
    TRAN_XOS = PhoneOsInfo(key='TRAN_XOS', vendor_name='transsion', os_name='xos', props_keyword='[xos]', launcher='com.transsion.XOSLauncher')
    TRAN_ITELOS = PhoneOsInfo(key='TRAN_ITELOS', vendor_name='transsion', os_name='itelos', props_keyword='[itelos]', launcher='com.transsion.itel.launcher')
    VIVO_FUNTOUCH = PhoneOsInfo(key='VIVO_FUNTOUCH', vendor_name='vivo', os_name='funtouch', props_keyword='Funtouch OS', launcher='com.android.launcher3')
    # VIVO_ORIGIN = PhoneOsInfo(key='VIVO_ORIGIN', vendor_name='vivo', os_name='origin', props_keyword='[Funtouch OS 15]', launcher='com.android.launcher3')
