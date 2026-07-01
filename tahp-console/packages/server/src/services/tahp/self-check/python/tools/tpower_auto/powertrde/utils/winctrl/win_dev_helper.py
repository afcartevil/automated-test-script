import ctypes
from ctypes import wintypes, byref, create_unicode_buffer
from typing import Dict, Optional, Callable, Generator, Set

from powertrde.framework.logs_protocol import logs_p

if ctypes.sizeof(ctypes.c_void_p) == 8:
    TYPE_PTR = ctypes.c_uint64
else:
    TYPE_PTR = ctypes.c_uint32


class DeviceInfoQueryResult:
    def __init__(self):
        self.instance_id: str = ""
        self.parent_id: str = ""
        self.request_properties: Dict[int, Optional[str]] = {}


# Define GUID and TYPE_PTR for both 32-bit and 64-bit systems
class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", wintypes.BYTE * 8)
    ]


# Define SpDevInfoData structure
class SpDevInfoData(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("ClassGuid", GUID),
        ("DevInst", wintypes.DWORD),
        ("Reserved", TYPE_PTR)
    ]

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.cbSize = ctypes.sizeof(self)


class Win32DevMgrHelper:
    __instance = None
    # Define constants
    DIG_CF_PRESENT = 0x00000002
    DIG_CF_ALL_CLASSES = 0x00000004
    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

    # SetupDiGetDeviceRegistryPropertyW constants
    SPDRP_DEVICEDESC = 0x00000000
    SPDRP_HARDWAREID = 0x00000001
    SPDRP_COMPATIBLEIDS = 0x00000002
    SPDRP_SERVICE = 0x00000004
    SPDRP_CLASS = 0x00000007
    SPDRP_CLASSGUID = 0x00000008
    SPDRP_DRIVER = 0x00000009
    SPDRP_CONFIGFLAGS = 0x0000000A
    SPDRP_MFG = 0x0000000B
    SPDRP_FRIENDLYNAME = 0x0000000C
    SPDRP_LOCATION_INFORMATION = 0x0000000D
    SPDRP_PHYSICAL_DEVICE_OBJECT_NAME = 0x0000000E
    SPDRP_CAPABILITIES = 0x0000000F
    SPDRP_REMOVAL_POLICY_HW_DEFAULT = 0x00000020

    @staticmethod
    def get_instance():
        if not Win32DevMgrHelper.__instance:
            Win32DevMgrHelper.__instance = Win32DevMgrHelper()
        return Win32DevMgrHelper.__instance

    def __init__(self):
        # Load SetupAPI DLL
        self._setup_api = ctypes.windll.setupapi
        self._cfgmgr32 = ctypes.windll.cfgmgr32

        # Setup function signatures
        self._setup_api.SetupDiGetClassDevsW.restype = wintypes.HANDLE
        self._setup_api.SetupDiGetClassDevsW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR, wintypes.HWND,
                                                         wintypes.DWORD]

        self._setup_api.SetupDiEnumDeviceInfo.restype = wintypes.BOOL
        self._setup_api.SetupDiEnumDeviceInfo.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                                          ctypes.POINTER(SpDevInfoData)]

        self._setup_api.SetupDiGetDeviceInstanceIdW.restype = wintypes.BOOL
        self._setup_api.SetupDiGetDeviceInstanceIdW.argtypes = [wintypes.HANDLE, ctypes.POINTER(SpDevInfoData),
                                                                wintypes.LPWSTR,
                                                                wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]

        self._setup_api.SetupDiDestroyDeviceInfoList.restype = wintypes.BOOL
        self._setup_api.SetupDiDestroyDeviceInfoList.argtypes = [wintypes.HANDLE]

        self._setup_api.SetupDiGetDeviceRegistryPropertyW.restype = wintypes.BOOL
        self._setup_api.SetupDiGetDeviceRegistryPropertyW.argtypes = [wintypes.HANDLE, ctypes.POINTER(SpDevInfoData),
                                                                      wintypes.DWORD,
                                                                      ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p,
                                                                      wintypes.DWORD,
                                                                      ctypes.POINTER(wintypes.DWORD)]

        self._cfgmgr32.CM_Get_Parent.restype = wintypes.DWORD
        self._cfgmgr32.CM_Get_Parent.argtypes = [ctypes.POINTER(wintypes.DWORD), wintypes.DWORD, wintypes.DWORD]

        self._cfgmgr32.CM_Get_Device_IDW.restype = wintypes.DWORD
        self._cfgmgr32.CM_Get_Device_IDW.argtypes = [wintypes.DWORD, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]

    def query_devices_info(self, request_properties: Optional[Set[int]], predicate: Optional[Callable[[str], bool]]) \
            -> Generator[Optional[DeviceInfoQueryResult], None, Optional[DeviceInfoQueryResult]]:
        device_info_set = None
        try:
            device_info_set = self._get_device_info_set()
            dev_info_data = SpDevInfoData()
            first_result: Optional[DeviceInfoQueryResult] = None
            for result in self._query_devices_info(device_info_set, dev_info_data, request_properties, predicate):
                if not first_result:
                    first_result = result
                yield result
        except Exception as e:
            logs_p().log_exception(f"Error query devices info: {e}")
            return None
        finally:
            if device_info_set:
                self._setup_api.SetupDiDestroyDeviceInfoList(device_info_set)
        return first_result

    # Function to get handle to device information set
    def _get_device_info_set(self):
        device_info_set = self._setup_api.SetupDiGetClassDevsW(None, None, None,
                                                               Win32DevMgrHelper.DIG_CF_PRESENT |
                                                               Win32DevMgrHelper.DIG_CF_ALL_CLASSES)
        if device_info_set == Win32DevMgrHelper.INVALID_HANDLE_VALUE:
            raise ctypes.WinError()
        return device_info_set

    def _query_devices_info(self, device_info_set, dev_info_data: SpDevInfoData,
                            request_properties: Set[int], predicate: Callable[[str], bool]) \
            -> Generator[Optional[DeviceInfoQueryResult], None, None]:
        index = 0
        while self._setup_api.SetupDiEnumDeviceInfo(device_info_set, index, byref(dev_info_data)):
            index += 1
            # Retrieve device ID
            device_id = self._get_device_id(device_info_set, dev_info_data)
            if device_id:
                if not predicate or predicate(device_id):
                    last_result = DeviceInfoQueryResult()
                    last_result.instance_id = device_id
                    last_result.parent_id = self._get_parent_device_id(dev_info_data.DevInst)
                    if request_properties:
                        for prop in request_properties:
                            last_result.request_properties[prop] = self._get_device_property(device_info_set,
                                                                                             dev_info_data, prop)
                    yield last_result

    def _get_device_id(self, device_info_set, dev_info_data) -> str:
        buffer = create_unicode_buffer(200)
        if self._setup_api.SetupDiGetDeviceInstanceIdW(device_info_set, byref(dev_info_data), buffer, len(buffer),
                                                       None):
            return buffer.value
        return ""

    def _get_parent_device_id(self, dev_inst) -> str:
        parent_dev_inst = wintypes.DWORD()
        if self._cfgmgr32.CM_Get_Parent(byref(parent_dev_inst), dev_inst, 0) == 0:
            buffer = create_unicode_buffer(200)
            if self._cfgmgr32.CM_Get_Device_IDW(parent_dev_inst.value, buffer, len(buffer), 0) == 0:
                return buffer.value
        return ""

    # Function to get device registry property
    def _get_device_property(self, device_info_set, dev_info_data, property_index) -> Optional[str]:
        # buffer = (ctypes.c_wchar * 256)()
        buffer = create_unicode_buffer(1024)
        property_reg_data_type = wintypes.DWORD()
        required_size = wintypes.DWORD()

        if self._setup_api.SetupDiGetDeviceRegistryPropertyW(device_info_set, byref(dev_info_data), property_index,
                                                             byref(property_reg_data_type), byref(buffer),
                                                             ctypes.sizeof(buffer), byref(required_size)):
            return buffer.value
        else:
            return None
