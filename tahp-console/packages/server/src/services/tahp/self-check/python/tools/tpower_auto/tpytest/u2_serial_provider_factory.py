from typing import Union

from powertrde.framework.lazy_device_id import SerialProvider, CachedSerialProvider


class U2SerialProviderFactory:
    def __init__(self, root_provider):
        super().__init__()
        self.root_provider = root_provider

    @property
    def serial_provider(self) -> Union[None, SerialProvider, CachedSerialProvider]:
        return self.root_provider.u2d

    @property
    def serial(self) -> str:
        return self.root_provider.device_id


class CopilotU2SerialProviderFactory:
    def __init__(self, copilot_root_provider):
        super().__init__()
        self.copilot_root_provider = copilot_root_provider

    @property
    def serial_provider(self) -> Union[None, SerialProvider, CachedSerialProvider]:
        return self.copilot_root_provider.c_u2d

    @property
    def serial(self) -> str:
        return self.copilot_root_provider.c_device_id
