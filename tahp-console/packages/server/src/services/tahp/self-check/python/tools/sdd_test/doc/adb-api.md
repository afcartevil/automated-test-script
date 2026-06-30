# ADB 方法清单

文件：`src/utils/adb/adb_utils.py`

> 说明：以下均为框架当前可调用方法。最小使用示例见 `doc/minimal-cases/case-adb-methods.md`。

## 1. 命令执行与基础属性

- `execute_command(command, timeout=None, shell=False, cwd=None, env=None)`
  - 执行系统命令，返回结构化字典（`success/output/error/return_code/...`）。
- `adb_shell(device_serial, shell_command, timeout=30, no_retry=False)`
  - 执行设备侧 shell 命令，返回与 `execute_command` 一致的结构化字典。
- `getprop(prop_key, sn=None)`
  - 读取设备属性。
- `get_first_sn()`
  - 获取 `adb devices` 的第一台设备 SN。

## 2. 资源与文件类

- `is_apk_exist(device_serial, apk_name)`
- `is_file_exist(device_serial, file_path)`
- `find_file_in_trregion_etc_asset(device_serial, file_name)`
- `pull_file(device_serial, remote_path, local_path)`
- `ls_dir(device_serial, dir_name)`
- `is_dir_exist(device_serial, path)`
- `adb_cat(device_serial, file_path)`

## 3. 设备能力与特征判断

- `is_uniform_patchtime(device_serial)`
- `get_feature(device_serial, feature_name)`
- `is_google_one_product(device_serial)`
- `is_root_product(device_serial)`
- `is_tssi_product(device_serial)`
- `is_package_exist(device_serial, package_name)`
- `get_apkpath_by_package(device_serial, package_name)`
- `get_desktop_widget(device_serial)`

## 4. 设备规格读取（供 marker 判断）

- `get_device_android_version(device_serial)`
- `get_device_ram_size(device_serial)`
- `get_device_fps(device_serial)`
- `get_tOS_version(device_serial)`
- `is_GO_device(device_serial)`
- `is_slim_device(device_serial)`
- `is_cuttlefish_device(device_serial)`：判定 MTK CuttleFish 类虚拟设备（`ro.product.vendor.model` 含固定参考串且 `ro.product.device == cs_arm64_only`），供 `require_non_cuttlefish` marker 使用
- `get_soc_paltform(device_serial)`
- `get_kernel_version(device_serial)`

## 5. 返回值约定

- 纯查询方法一般返回字符串、布尔值或列表。
- `execute_command` 与 `adb_shell` 返回统一字典，推荐优先判定 `success` 后再读 `output`。
- 发生异常时多数方法返回 `False`、`None` 或默认值（如 `0`）。

## 6. 使用建议

- 新增 ADB 方法时尽量复用 `execute_command`，保持返回结构一致。
- 需要重试能力的方法优先通过 `@adb_repeat` 间接使用 `execute_command`。
- 业务用例中尽量不要直接拼大量 shell，建议在本文件扩展后复用。
- 生成用例时建议先调用 `adb_shell()` 保存结果，再单独断言 `success` 和 `output`，方便定位是命令执行失败还是输出不符合预期。
