from enum import Enum
from typing import Set

from tpy_aw.aw_defines import PhoneOsInfo


class SupportedOS(Enum):
    UNKNOWN = PhoneOsInfo(key='UNKNOWN', vendor_name='', os_name='unknown', props_keyword='[unknown os]', launcher='com.android.launcher3', extra_env_keys=[])

    # 平板
    TRAN_XOSPAD_TOS16 = PhoneOsInfo(key='TRAN_XOSPAD_TOS16', vendor_name='transsion', os_name='xospad', props_keyword='@:tran_xospad_16_filter', launcher='com.transsion.launcher3', extra_env_keys=['TOS16', 'PAD', 'XOSPAD_TOS16'])

    TRAN_HIOS_TOS16 = PhoneOsInfo(key='TRAN_HIOS_TOS16', vendor_name='transsion', os_name='hios', props_keyword='@:tran_hios_16_filter', launcher='com.transsion.launcher3', extra_env_keys=['TOS16'])
    TRAN_XOS_TOS16 = PhoneOsInfo(key='TRAN_XOS_TOS16', vendor_name='transsion', os_name='xos', props_keyword='@:tran_xos_16_filter', launcher='com.transsion.launcher3', extra_env_keys=['TOS16'])
    TRAN_ITELOS_TOS16 = PhoneOsInfo(key='TRAN_ITELOS_TOS16', vendor_name='transsion', os_name='itelos', props_keyword='@:tran_itelos_16_filter', launcher='com.transsion.launcher3', extra_env_keys=['TOS16'])

    TRAN_HIOS = PhoneOsInfo(key='TRAN_HIOS', vendor_name='transsion', os_name='hios', props_keyword='[hios]', launcher='com.transsion.hilauncher', extra_env_keys=[])
    TRAN_XOS = PhoneOsInfo(key='TRAN_XOS', vendor_name='transsion', os_name='xos', props_keyword='[xos]', launcher='com.transsion.XOSLauncher', extra_env_keys=[])
    TRAN_ITELOS = PhoneOsInfo(key='TRAN_ITELOS', vendor_name='transsion', os_name='itelos', props_keyword='[itelos]', launcher='com.transsion.itel.launcher', extra_env_keys=[])

    VIVO_FUNTOUCH = PhoneOsInfo(key='VIVO_FUNTOUCH', vendor_name='vivo', os_name='funtouch', props_keyword='Funtouch OS', launcher='com.android.launcher3', extra_env_keys=[])
    VIVO_ORIGIN = PhoneOsInfo(key='VIVO_ORIGIN', vendor_name='vivo', os_name='origin', props_keyword='OriginOS', launcher='com.bbk.launcher2', extra_env_keys=[])

    OPPO_REALMEUI = PhoneOsInfo(key='OPPO_REALMEUI', vendor_name='oppo', os_name='realmeui', props_keyword='ro.build.version.realmeui', launcher='com.android.launcher', extra_env_keys=[])
    OPPO_COLOROS = PhoneOsInfo(key='OPPO_COLOROS', vendor_name='oppo', os_name='coloros', props_keyword='com.coloros.', launcher='com.android.launcher', extra_env_keys=[])

    XIAOMI_HYPER_R = PhoneOsInfo(key='XIAOMI_HYPER_R', vendor_name='xiaomi', os_name='hyper_r', props_keyword='@:xiaomi_hyper_r_filter', launcher='com.miui.home', extra_env_keys=[])
    XIAOMI_HYPER = PhoneOsInfo(key='XIAOMI_HYPER', vendor_name='xiaomi', os_name='hyper', props_keyword='[ro.mi.os.version.code]', launcher='com.mi.android.globallauncher', extra_env_keys=[])

    SAMSUNG = PhoneOsInfo(key='SAMSUNG', vendor_name='samsung', os_name='galaxy', props_keyword='[samsung]', launcher='com.sec.android.app.launcher', extra_env_keys=[])

    @staticmethod
    def get_all_launchers() -> Set[str]:
        ret = set()
        for os_enum in SupportedOS:
            ret.add(os_enum.value.launcher)
        return ret

    @staticmethod
    def _is_os_version_at_least(props: str, os_version_at_least: int):
        """
            高效判断 adb props 文本中 [ro.build.version.release] 是否存在且为整数 >= {os_version_at_least}。
            - 若找不到该 key 或值不是纯整数 -> 返回 False。
            - 不使用正则，只做最小范围的 find 操作以提高性能。
            """
        if not props:
            return False

        key = '[ro.build.version.release]:'
        idx = props.find(key)
        if idx == -1:
            return False

        # 在 key 之后寻找方括号内的值（最小范围查找）
        start = props.find('[', idx + len(key))
        if start == -1:
            return False
        end = props.find(']', start + 1)
        if end == -1:
            return False

        val = props[start + 1:end]
        if not val:
            return False

        # 严格要求为纯数字（整数），否则返回 False
        if not val.isdigit():
            return False

        try:
            version_num = int(val)
        except Exception:
            return False

        return version_num >= os_version_at_least

    @staticmethod
    def tran_xos_16_filter(props_text: str):
        if not SupportedOS._is_os_version_at_least(props_text, 16):
            return False

        return '[Infinix]' in props_text

    @staticmethod
    def tran_xospad_16_filter(props_text: str):
        _is_xos_16 = SupportedOS.tran_xos_16_filter(props_text)
        _is_pad = any(x in props_text for x in ['[ro.tr_device.type]: [tablet]', '[ro.build.characteristics]: [tablet]'])
        return _is_xos_16 and _is_pad

    @staticmethod
    def tran_hios_16_filter(props_text: str):
        if not SupportedOS._is_os_version_at_least(props_text, 16):
            return False

        return '[hios]' in props_text

    @staticmethod
    def tran_itelos_16_filter(props_text: str):
        if not SupportedOS._is_os_version_at_least(props_text, 16):
            return False

        return '[itelos]' in props_text

    @staticmethod
    def xiaomi_hyper_r_filter(props_text: str):
        return '[ro.mi.os.version.code]' in props_text and '[Redmi]' in props_text
