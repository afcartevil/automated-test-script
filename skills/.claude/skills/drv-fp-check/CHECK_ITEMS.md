# DRV_FP_Check 检查项规则

本文是 `DRV_FP_Check` 的详细检查规则。执行时以目标项目为边界，参考路径中的项目名、SoC 和 kernel 版本必须替换为用户指定项目。

## 0. 升级前后路径定位

执行检查时先确定两个根路径：

- **升级前产品根路径**：优先使用用户提供的具体产品根目录。常见结构为 `tran_projects/<family>/<project_variant>/<product>`，例如 `tran_projects/x6885/x6885_h8923_m1/x6885`。
- **升级后工作区根路径**：当前右侧工作区或用户指定升级后代码根目录。

路径模板如下，示例中的 `x6885_h8923`、`mt6789`、`kernel-5.10`、`kernel_device_modules-6.12` 只能作为参考，实际检查必须替换为目标项目、SoC 和 kernel 版本。

| 检查项 | 升级前参考路径 | 升级后参考路径 |
| --- | --- | --- |
| 驱动 | `kernel/kernel_device_modules-<ver>/drivers/input/fingerprint` | `kernel/kernel_device_modules-<ver>/drivers/input/fingerprint` |
| DTS | `<pre_product_root>/kernel-<ver>/arch/arm64/boot/dts/mediatek/<project>.dts` | `kernel/kernel_device_modules-<ver>/arch/arm64/boot/dts/mediatek/<project>.dts` |
| Preloader DWS | `<pre_product_root>/vendor/mediatek/proprietary/bootable/bootloader/preloader/custom/<project>/dct/dct/codegen.dws` | `vendor/mediatek/proprietary/bootable/bootloader/preloader/custom/<project>/dct/dct/codegen.dws` |
| Kernel DCT DWS | `<pre_product_root>/vendor/mediatek/proprietary/custom/<project>/kernel/dct/dct/codegen.dws` | `vendor/mediatek/proprietary/custom/<project>/kernel/dct/dct/codegen.dws` |
| Tools DWS | `<pre_product_root>/vendor/mediatek/proprietary/tools/dct/dws/<soc>/<project>.dws` | `vendor/mediatek/proprietary/tools/dct/dws/<soc>/<project>.dws` |

X6885 示例：

- 升级前 DTS：`tran_projects/x6885/x6885_h8923_m1/x6885/kernel-5.10/arch/arm64/boot/dts/mediatek/x6885_h8923.dts`
- 升级后 DTS：`kernel/kernel_device_modules-6.12/arch/arm64/boot/dts/mediatek/x6885_h8923.dts`
- 升级前 DWS 三处：
  - `tran_projects/x6885/x6885_h8923_m1/x6885/vendor/mediatek/proprietary/bootable/bootloader/preloader/custom/x6885_h8923/dct/dct/codegen.dws`
  - `tran_projects/x6885/x6885_h8923_m1/x6885/vendor/mediatek/proprietary/custom/x6885_h8923/kernel/dct/dct/codegen.dws`
  - `tran_projects/x6885/x6885_h8923_m1/x6885/vendor/mediatek/proprietary/tools/dct/dws/mt6789/x6885_h8923.dws`
- 升级后 DWS 三处：
  - `vendor/mediatek/proprietary/bootable/bootloader/preloader/custom/x6885_h8923/dct/dct/codegen.dws`
  - `vendor/mediatek/proprietary/custom/x6885_h8923/kernel/dct/dct/codegen.dws`
  - `vendor/mediatek/proprietary/tools/dct/dws/mt6789/x6885_h8923.dws`

若升级前项目不是 `kernel-<ver>` 结构，而是直接提供 `kernel/kernel_device_modules-<ver>` 或 `kernel_device_modules-<ver>`，按实际目录替换模板；找不到升级前目标文件时该项标记 BLOCKED。

## 1. rc 和 xml 配置

目标文件：

- `vendor/transsion/projects/<project>/device-vext.mk`

检查四行 fingerprint 配置是否存在且是否生效：

```makefile
PRODUCT_COPY_FILES += frameworks/native/data/etc/android.hardware.fingerprint.xml:$(TARGET_COPY_OUT_ODM)/etc/permissions/android.hardware.fingerprint.xml
PRODUCT_COPY_FILES += hardware/interfaces/biometrics/fingerprint/aidl/transsion/fingerprint-default.xml:$(TARGET_COPY_OUT_ODM)/etc/vintf/manifest/fingerprint-default.xml
PRODUCT_COPY_FILES += hardware/interfaces/biometrics/fingerprint/aidl/transsion/fingerprint-default.rc:$(TARGET_COPY_OUT_ODM)/etc/init/fingerprint-default.rc
PRODUCT_COPY_FILES += vendor/transsion/vendor_modules/fingerprint/transsion/hal/binder/manifest_transsion.xml:$(TARGET_COPY_OUT_ODM)/etc/vintf/manifest/manifest_transsion.xml
```

判断表：

| 项目状态 | fingerprint.xml | fingerprint-default.xml | fingerprint-default.rc | manifest_transsion.xml |
| --- | --- | --- | --- | --- |
| 无指纹 IC | 应注释 / 不生效 | 应注释 / 不生效 | 应注释 / 不生效 | 应注释 / 不生效 |
| 非归一化 + GOODIX GW9598 | 应生效 | 应生效 | 应生效 | 应生效 |
| 非归一化 + 其它 IC | 应生效 | 应生效 | 应生效 | 应注释 / 不生效 |
| 归一化 | 应生效 | 应生效 | 应生效 | 应生效 |

注意：

- “注释”可以是行首 `#`，也可以是未包含在实际构建条件中；输出时说明判定依据。
- 若无法确认项目是否有指纹 IC、IC 型号或架构，不要给 PASS，标记 BLOCKED。
- 若 `device-vext.mk` 通过 include 或变量间接添加配置，需要追踪实际生效路径。

## 2. DTS 指纹 GPIO

目标文件示例：

- `kernel/kernel_device_modules-<ver>/arch/arm64/boot/dts/mediatek/<project>.dts`
- 升级前路径按“0. 升级前后路径定位”中的 DTS 模板查找。

检查对象：

- `fingerprint` / `fingerprint@*` 节点。
- fingerprint 节点引用的 `pinctrl-*` label。
- 相关 `&pio` pinctrl 配置。

必须与升级前目标项目配置一致的重点字段：

- `compatible`
- `reg`
- `spi-max-frequency`
- `interrupt-parent`
- `interrupts`
- `debounce`
- `irq-gpio`
- `reset-gpio`
- power GPIO / supply
- `pinctrl-names`
- `pinctrl-*`
- `status`
- SPI 相关 pinmux / pull / output 状态

判断规则：

- 只对齐指纹实际使用的 GPIO、power 和 SPI 引脚。
- 与升级前不一致时，必须判断是否有明确的硬件变更依据；无依据则标记 FAIL。
- 不要因为全文件 diff 修改或报错无关外设。

## 3. 三处 DWS 指纹 GPIO

目标文件：

- `vendor/mediatek/proprietary/bootable/bootloader/preloader/custom/<project>/dct/dct/codegen.dws`
- `vendor/mediatek/proprietary/custom/<project>/kernel/dct/dct/codegen.dws`
- `vendor/mediatek/proprietary/tools/dct/dws/<soc>/<project>.dws`

升级前同三处路径必须从 `<pre_product_root>/vendor/mediatek/proprietary/...` 下读取；不能把升级后 `vendor/mediatek/proprietary/...` 路径直接套到升级前仓库根目录。

检查步骤：

1. 先从升级后 DTS fingerprint 节点提取实际使用的 IRQ、reset、power、SPI 引脚。
2. 到升级前三处 DWS 中确认这些引脚的模式、方向、上下拉、默认电平等配置。
3. 到升级后三处 DWS 中逐项核对是否一致。
4. 三处分别输出结果，不能只写“DWS 已检查”。

判断规则：

- 三处都一致：PASS。
- 任一处指纹相关引脚不一致且无硬件变更依据：FAIL。
- 缺升级前 DWS、目标 DWS 或无法定位 SoC/project：BLOCKED。

## 4. 指纹键值 `tran-keys`

命令：

```shell
adb shell getevent -ltr
```

检查输出是否包含：

```text
tran-keys
```

判断规则：

- 包含 `tran-keys`：PASS，记录 input 设备名和事件路径。
- 不包含 `tran-keys`：FAIL，建议回查 DTS/DWS GPIO、驱动 input 注册、kernel log。
- adb 无设备、无权限、用户未连接手机：BLOCKED。

## 5. 驱动与 DTS compatible

检查路径：

- `kernel/kernel_device_modules-<ver>/drivers/input/fingerprint/tran_common`
- `kernel/kernel_device_modules-<ver>/drivers/input/fingerprint/tran_common_v2`
- `kernel/kernel_device_modules-<ver>/arch/arm64/boot/dts/mediatek/<project>.dts`

升级前驱动参考 `kernel/kernel_device_modules-<ver>/drivers/input/fingerprint`，用于判定原项目归一化 / 非归一化；升级后驱动参考同结构路径，用于检查当前驱动是否匹配。

判断规则：

| 架构 | 驱动目录 | 驱动 compatible | DTS compatible |
| --- | --- | --- | --- |
| 非归一化 | `tran_common` | `.compatible = "tran_fp_legacy"` | 应与驱动匹配为 `tran_fp_legacy` |
| 归一化 | `tran_common_v2` | `.compatible = "tran_fp"` | 应与驱动匹配为 `tran_fp` |

冲突处理：

- 用户说非归一化但仅存在 `tran_common_v2`：BLOCKED 或 FAIL，需结合升级前架构确认。
- 用户说归一化但仅存在 `tran_common`：BLOCKED 或 FAIL，需结合升级前架构确认。
- 两套驱动同时存在：BLOCKED，提示用户确认目标架构和实际编译路径。
- 驱动 `.compatible` 与 DTS `compatible` 不一致：FAIL。

## 6. 检查结论分级

- **PASS**：检查项满足规则，有文件或命令输出证据。
- **FAIL**：检查项明确不满足规则，需要修复。
- **BLOCKED**：缺少项目背景、升级前配置、目标文件、adb 设备或架构信息，无法可靠判断。

存在风险但指纹 GPIO 数值与升级前一致时（例如 Kernel DCT DWS 的 `chip` 头信息错误）：汇总表结论写 **PASS**，备注写 `风险：...`，在对应 3.x 详细说明的「问题」中描述。

## 7. 固定输出格式

检查报告**必须**按 [SKILL.md](SKILL.md) 第三节输出：**基础信息一行 + 指纹/人脸分表汇总 + 总体结论 + 建议动作**。

硬性要求：

1. 汇总表列名固定为：`检查项 | 结论 | 说明`。
2. **指纹表**顺序：rc/xml → fp_fw → DTS → DWS → 驱动 → tran-keys（仅做指纹检查时只输出此表）。
3. **人脸表**顺序：Face HAL 初始化 → 人脸服务 → 人脸算法版本（仅做人脸检查时只输出此表）。
4. 默认不写长文明细；用户要求「详细」时再补充 log 片段。
5. FAIL/BLOCKED 在「说明」列写清关键证据（一句）。
6. 全 PASS 无风险时，「建议动作」写「无」。

## 8. Face HAL 初始化（开机 log）

### 代码参考

| 模块 | 路径 | 作用 |
| --- | --- | --- |
| AIDL | `hardware/interfaces/biometrics/face/aidl/default/main.cpp` | 打印 `Face HAL started` |
| AIDL | `.../Face.cpp` | 打印 `Face() done!` |
| AIDL | `.../FakeFaceEngine.cpp` | 打印 `GetSensorStrength CONVENIENCE` |
| HAL | `vendor/transsion/vendor_modules/face/face_hal/FaceTools.hpp` | 打印 `FaceHal_Version:` |
| HAL | `.../face_hal/FaceHal.cpp` | `face_algorithm_init()`，成功时 `ret: 0` |

### 前置条件

- 用户**必须**提供开机 log 文件路径（可为主 log、logcat 导出文件等）。
- 未提供 log 路径：该项 **BLOCKED**，说明「需提供开机 log 路径」。

### 检查方法

在用户提供的 log 中搜索（建议 tag：`android.hardware.biometrics.face-service`、`FaceHalHW`）：

**必须项（全部满足才 PASS）**

| 序号 | 关键字 / 模式 | 含义 |
| --- | --- | --- |
| 1 | `GetSensorStrength CONVENIENCE` | AIDL 侧传感器强度 |
| 2 | `Face HAL started` | Face AIDL 服务 main 启动 |
| 3 | `Face() done!` | Face 对象构造完成 |
| 4 | `FaceHal_Version:` | HAL 工具版本打印 |
| 5 | `face_algorithm_init begin` | 算法 init 开始 |
| 6 | `face_algorithm_init st_version:` | 算法库版本（与第 10 节联动） |
| 7 | `face_algorithm_init ret: 0` | license 与 `st_face_init_license` 成功 |
| 8 | `face_algorithm_init done` | 算法 init 结束 |
| 9 | `create Session, sensorId=` | Session 创建 |
| 10 | `face_set_active_group` 且 `store_path:` 非空 | 用户组与存储路径设置 |

**直接判 FAIL 的 log**

- `read license failed`
- `face unlock not support`
- `face_algorithm_init ret:` 后跟非 `0` 的返回值
- `face_set_active_group st_auth_init failed`
- `face_set_active_group st_auth_set_identifier failed`

**不作为初始化失败（说明中可注「无录入数据」）**

- `st_auth_get_template_info failed1. ret = 203` / `204`
- `face_remove user id not exist`

### 判定

- 必须项齐全且 `ret: 0`：**PASS**
- 缺少必须项或出现 FAIL 类 log：**FAIL**
- 无 log 路径：**BLOCKED**

## 9. 人脸服务（adb）

### 命令

```shell
adb shell "ps -A | grep face"
```

### 判定

| 结果 | 结论 |
| --- | --- |
| 输出包含 `android.hardware.biometrics.face-service` | **PASS** |
| 不包含上述进程名 | **FAIL** |
| adb 无设备 / 命令失败 | **BLOCKED** |

说明列建议写出匹配行摘要（pid、进程名）。

## 10. 人脸算法版本（开机 log）

### 前置条件

- 与第 8 节相同，**必须**有用户提供的开机 log 路径；否则 **BLOCKED**。

### 检查方法

在 log 中查找：

```text
face_algorithm_init st_version: <版本字符串>
```

该字符串来自 `FaceHal.cpp` 中 `st_auth_get_version()` 的返回值。

### 判定

| 结果 | 结论 |
| --- | --- |
| 找到非空 `st_version` 且同次 init 的 `ret: 0` | **PASS**，说明列写完整版本号 |
| 有 init 但 `ret` 非 0 | **FAIL** |
| 无 `st_version` 行 | **FAIL**（或 init 未执行，与第 8 节一并失败） |
| 无 log 路径 | **BLOCKED** |

### 与期望版本对比

若用户提供了期望算法版本，在说明列对比「实际 vs 期望」；未提供期望版本时只记录实际 `st_version`，不判 FAIL。

