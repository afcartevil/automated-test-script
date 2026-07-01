from dataclasses import dataclass


@dataclass(frozen=True)
class PhoneOsInfo:
    key: str
    vendor_name: str
    os_name: str
    props_keyword: str
    launcher: str
