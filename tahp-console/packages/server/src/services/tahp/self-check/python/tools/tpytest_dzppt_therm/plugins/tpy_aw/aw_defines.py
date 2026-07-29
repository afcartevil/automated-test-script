from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class PhoneOsInfo:
    key: str
    vendor_name: str
    os_name: str
    props_keyword: str
    launcher: str
    extra_env_keys: List[str]

    @property
    def is_transsion_os(self):
        return self.vendor_name == 'transsion'
