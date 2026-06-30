# 最小用例：ADB 方法

以下示例覆盖 `src/utils/adb/adb_utils.py` 中所有公开方法。示例代码仅用于参考，请复制到真实 `.py` 文件执行。

## 1. 命令执行与属性

```python
from src.utils.adb.adb_utils import execute_command, getprop, get_first_sn

sn = get_first_sn()
result = execute_command(f"adb -s {sn} shell getprop ro.build.display.id")
version = getprop("ro.build.display.id", sn)
print(result["success"], version)
```

```python
from src.utils.adb.adb_utils import adb_shell

sn = "YOUR_SN"
shell_command = "find /sys/devices/platform/odm -name tran_led_cmd"
expected_output = "/sys/devices/platform/odm/odm:tran_led_core/tran_led_cmd"

result = adb_shell(sn, shell_command, no_retry=True)
actual_output = result["output"].strip()
error_message = result["error"] or result["exception_msg"]

assert result["success"], (
    f"ADB命令执行失败: {shell_command}; "
    f"return_code={result['return_code']}; error={error_message}"
)
assert expected_output in actual_output, (
    f"ADB命令输出不符合预期: expected contains: {expected_output}; "
    f"actual: {actual_output}"
)
```

## 2. 文件与目录

```python
from src.utils.adb.adb_utils import (
    is_apk_exist,
    is_file_exist,
    find_file_in_trregion_etc_asset,
    pull_file,
    ls_dir,
    is_dir_exist,
    adb_cat,
)

sn = "YOUR_SN"
print(is_apk_exist(sn, "Settings.apk"))
print(is_file_exist(sn, "/system/build.prop"))
print(find_file_in_trregion_etc_asset(sn, "channel_list.xml"))
print(ls_dir(sn, "/system"))
print(is_dir_exist(sn, "/system/etc"))
print(adb_cat(sn, "/system/build.prop"))
print(pull_file(sn, "/system/build.prop", "./build.prop"))
```

## 3. 能力判断与包信息

```python
from src.utils.adb.adb_utils import (
    is_uniform_patchtime,
    get_feature,
    is_google_one_product,
    is_root_product,
    is_tssi_product,
    is_package_exist,
    get_apkpath_by_package,
    get_desktop_widget,
)

sn = "YOUR_SN"
print(is_uniform_patchtime(sn))
print(get_feature(sn, "android.hardware.camera.flash"))
print(is_google_one_product(sn))
print(is_root_product(sn))
print(is_tssi_product(sn))
print(is_package_exist(sn, "com.android.settings"))
print(get_apkpath_by_package(sn, "com.android.settings"))
print(get_desktop_widget(sn))
```

## 4. 设备规格读取

```python
from src.utils.adb.adb_utils import (
    get_device_android_version,
    get_device_ram_size,
    get_device_fps,
    get_tOS_version,
    is_GO_device,
    is_slim_device,
    get_soc_paltform,
    get_kernel_version,
)

sn = "YOUR_SN"
print(get_device_android_version(sn))
print(get_device_ram_size(sn))
print(get_device_fps(sn))
print(get_tOS_version(sn))
print(is_GO_device(sn))
print(is_slim_device(sn))
print(get_soc_paltform(sn))
print(get_kernel_version(sn))
```
