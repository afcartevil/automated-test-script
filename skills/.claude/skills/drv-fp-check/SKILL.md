---
name: drv-fp-check
description: 检查 Transsion/MTK Android 升级项目指纹与人脸调试项：指纹 rc/xml、DTS/DWS GPIO、tran-keys、驱动 compatible；人脸 Face HAL 开机 log 初始化、adb face-service 进程、算法 st_version。当用户要求检查指纹配置、人脸服务、facehal 初始化、face 算法版本或生物识别调试项时使用；格式和边界参照 DRV_FP_Adapt。
---

# DRV_FP_Check - 升级项目指纹 / 人脸调试项检查

业务命名：**DRV_FP_Check**。本 Skill 用于指纹 P1 适配后、人脸服务集成后的配置与运行态检查；与 `DRV_FP_Adapt` 互补，原则上只做只读核对和结论输出，除非用户明确要求修复。

**当前版本**：`1.3.0`（正式版）。版本号、发布状态与维护规则见 [VERSION.md](VERSION.md)；变更历史见 [CHANGELOG.md](CHANGELOG.md)。

**触发场景**

- **指纹**：检查指纹调试项、rc/xml、DTS/DWS、tran-keys、驱动 compatible。
- **人脸**：检查人脸服务、Face HAL 初始化、人脸算法版本；用户需提供**开机 log 路径**（算法版本与 HAL 初始化均依赖 log）。

推荐用户一次提供：目标项目代号、平台/SoC、kernel 版本、指纹 IC 与架构信息、升级前后代码路径；做人脸检查时另提供**开机 log 文件路径**。

## 项目检查边界

- 必须先确认目标项目目录、升级前代码路径和升级后工作区；检查结论只针对用户指定项目。
- 文档中的 `x6885_h8923`、`mt6789`、`kernel_device_modules-6.12` 仅是参考路径，实际检查时必须替换为目标项目、目标平台和目标 kernel 版本。
- 升级前代码若包含 `tran_projects/<family>/<project_variant>/<product>/...` 结构，优先在该产品根目录下找 DTS / DWS；不要只在升级前仓库根目录下按升级后路径硬套。
- 未确认是否有指纹 IC、IC 厂商型号或归一化状态时，先做可读文件核对，并把无法判断项列为“待用户确认”。
- 不要因为其它项目或参考项目存在配置，就判定目标项目也必须一致；必须以目标项目自身需求和升级前配置为准。
- 若用户只要求检查，不要主动修改文件；需要修复时先输出风险和拟修改项。

## 编写规划

1. **先定基础信息**：确认项目是否有指纹 IC；若有，确认归一化/非归一化、IC 厂商与型号。
2. **再查 rc/xml**：检查目标项目 `device-vext.mk` 中 fingerprint permission、AIDL manifest、init rc、`manifest_transsion.xml` 是否应保留或注释。
3. **核对 GPIO**：DTS 与升级前 fingerprint 节点及 pinctrl 对齐；三处 DWS 只检查指纹相关 IRQ、reset、power、SPI 引脚。
4. **验证键值**：连接手机运行 `adb shell getevent -ltr`，检查输出是否包含 `tran-keys`。
5. **检查驱动**：根据归一化状态确认 `tran_common` / `tran_common_v2` 的 compatible；非归一化应为 `tran_fp_legacy`，归一化应为 `tran_fp`，并与 DTS `compatible` 一致。
6. **输出结论**：必须按本文「三、固定输出格式」生成**简洁表格汇总**；默认不写长段落明细，FAIL/BLOCKED 在「说明」列写清原因即可。

详细规则见 [CHECK_ITEMS.md](CHECK_ITEMS.md)。

---

## 一、检查前置条件

执行检查前尽量收集以下信息：

- 目标项目代号，例如 `x6885_h8923`、`lj8_h781`。
- 平台/SoC，例如 `mt6789`、`mt6878`。
- kernel 版本，例如 `kernel_device_modules-6.1`、`kernel_device_modules-6.12`。
- 项目是否有指纹 IC。
- 指纹架构：归一化 / 非归一化；未知时按 `DRV_FP_Adapt` 的驱动目录规则判定。
- 指纹 IC 厂商与型号，例如 GOODIX GW9598。
- 升级前代码路径，用于 DTS / DWS GPIO 对齐。
- 升级后工作区路径，用于当前配置检查。
- 升级前产品根路径（若存在），例如 `tran_projects/x6885/x6885_h8923_m1/x6885`；没有该结构时再按用户给出的升级前根路径查找。
- 若检查 `tran-keys`，需要已连接手机并允许执行 adb。

信息不足时不要跳过检查项，应标记为 **BLOCKED** 并说明缺少的信息。

---

## 二、检查工作流

### 1. rc 和 xml 配置检查

检查目标项目：

- `vendor/transsion/projects/<project>/device-vext.mk`

必须核对四类配置：

```makefile
PRODUCT_COPY_FILES += frameworks/native/data/etc/android.hardware.fingerprint.xml:$(TARGET_COPY_OUT_ODM)/etc/permissions/android.hardware.fingerprint.xml
PRODUCT_COPY_FILES += hardware/interfaces/biometrics/fingerprint/aidl/transsion/fingerprint-default.xml:$(TARGET_COPY_OUT_ODM)/etc/vintf/manifest/fingerprint-default.xml
PRODUCT_COPY_FILES += hardware/interfaces/biometrics/fingerprint/aidl/transsion/fingerprint-default.rc:$(TARGET_COPY_OUT_ODM)/etc/init/fingerprint-default.rc
PRODUCT_COPY_FILES += vendor/transsion/vendor_modules/fingerprint/transsion/hal/binder/manifest_transsion.xml:$(TARGET_COPY_OUT_ODM)/etc/vintf/manifest/manifest_transsion.xml
```

判断规则：

- **无指纹 IC**：以上四行都应注释或不生效。
- **有指纹 IC + 非归一化 + GOODIX GW9598**：以上四行都不需要注释。
- **有指纹 IC + 非归一化 + 其它 IC**：前三行保留，`manifest_transsion.xml` 这一行应注释或不生效。
- **有指纹 IC + 归一化**：以上四行都不需要注释。

### 2. 指纹 GPIO 引脚配置检查

**DTS 检查**

- 检查升级后 `kernel/kernel_device_modules-<ver>/arch/arm64/boot/dts/mediatek/<project>.dts`。
- 升级前优先检查 `<pre_product_root>/kernel-<ver>/arch/arm64/boot/dts/mediatek/<project>.dts`；若升级前代码直接提供 `kernel/kernel_device_modules-<ver>` 或 `kernel_device_modules-<ver>`，则检查其下 `arch/arm64/boot/dts/mediatek/<project>.dts`。
- 与升级前目标项目 DTS 对齐 fingerprint 节点和其引用的 pinctrl。
- 重点字段：`compatible`、`reg`、`spi-max-frequency`、`interrupt-parent`、`interrupts`、`debounce`、`irq-gpio`、`reset-gpio`、power GPIO / supply、`pinctrl-names`、`pinctrl-*`、`status`。

**DWS 检查**

检查三处 DWS，并与升级前配置一致：

升级后路径：

- `vendor/mediatek/proprietary/bootable/bootloader/preloader/custom/<project>/dct/dct/codegen.dws`
- `vendor/mediatek/proprietary/custom/<project>/kernel/dct/dct/codegen.dws`
- `vendor/mediatek/proprietary/tools/dct/dws/<soc>/<project>.dws`

升级前路径：在 `<pre_product_root>/vendor/mediatek/proprietary/...` 下查找同三处 DWS；若用户只提供升级前仓库根路径，先定位 `tran_projects/<family>/<project_variant>/<product>` 产品根路径。

只检查 DTS fingerprint 节点实际使用的 IRQ、reset、power、SPI 引脚；不要把无关外设差异列为指纹问题。

### 3. 指纹键值检查

连接手机后执行：

```shell
adb shell getevent -ltr
```

判断输出是否包含：

```text
tran-keys
```

- 找到 `tran-keys`：键值节点存在，记录对应输入设备。
- 未找到 `tran-keys`：标记 FAIL，建议结合 DTS/DWS、驱动 probe 和 input 注册日志继续排查。
- 无设备、adb 不可用或用户未要求连机：标记 BLOCKED。

### 4. 驱动配置检查

先判断项目归一化状态：

- **非归一化**：驱动采用 `drivers/input/fingerprint/tran_common`。
- **归一化**：驱动采用 `drivers/input/fingerprint/tran_common_v2`。

驱动参考路径：

- 升级前：`kernel/kernel_device_modules-<ver>/drivers/input/fingerprint`
- 升级后：`kernel/kernel_device_modules-<ver>/drivers/input/fingerprint`

检查驱动 compatible 是否与架构匹配：非归一化 `tran_common` 应为 `.compatible = "tran_fp_legacy"`；归一化 `tran_common_v2` 应为 `.compatible = "tran_fp"`。同时确认它们与 DTS 中 fingerprint 节点 `compatible` 字段匹配。

若驱动目录、DTS compatible 或用户提供的架构信息互相冲突，标记 FAIL 或 BLOCKED，并说明冲突证据。

---

## 二（续）、人脸检查工作流

人脸相关代码参考路径（升级后工作区）：

| 模块 | 路径 |
| --- | --- |
| AIDL 服务 | `hardware/interfaces/biometrics/face/aidl/default/`（`main.cpp`、`Face.cpp`、`face-default.rc`） |
| Face HAL | `vendor/transsion/vendor_modules/face/face_hal/`（`FaceHal.cpp`、`FaceTools.hpp`） |
| 算法库 | `vendor/transsion/vendor_modules/face/face_st/` |

服务进程名（`face-default.rc`）：`android.hardware.biometrics.face-service`

### 5. Face HAL 初始化检查（开机 log）

**前置**：用户必须提供开机 log 路径（如 `main_log` / `kernel_log`）；未提供则该项 **BLOCKED**。

在 log 中按顺序检索以下关键字（tag 多为 `android.hardware.biometrics.face-service` / `FaceHalHW`）：

| 阶段 | 必须出现的 log（节选） | 来源 |
| --- | --- | --- |
| AIDL 启动 | `GetSensorStrength CONVENIENCE` | `FakeFaceEngine.cpp` |
| AIDL 启动 | `Face HAL started` | `main.cpp` |
| AIDL 启动 | `Face() done!` | `Face.cpp` |
| 算法初始化 | `FaceHal_Version:` | `FaceTools.hpp` |
| 算法初始化 | `face_algorithm_init begin` | `FaceHal.cpp` |
| 算法初始化 | `face_algorithm_init st_version:` | `FaceHal.cpp`（`st_auth_get_version()`） |
| 算法初始化 | `face_algorithm_init ret: 0` | `FaceHal.cpp`（`st_face_init_license` 成功） |
| 算法初始化 | `face_algorithm_init done` | `FaceHal.cpp` |
| Session | `create Session, sensorId=` | AIDL Session |
| Session | `face_set_active_group` 且 store_path 正常 | `FaceHal.cpp` |

**PASS**：上述必须项均出现，且 `face_algorithm_init ret: 0`。

**FAIL**：缺少 `Face HAL started` / `Face() done!`；或 `face_algorithm_init ret` 非 0；或 `read license failed` / `face unlock not support`；或 `face_set_active_group st_auth_init failed`。

**不作为初始化失败**（可在说明中标注「无 enrolled 数据」）：`st_auth_get_template_info failed1. ret = 203/204`、`face_remove user id not exist`。

### 6. 人脸服务检查（adb）

```shell
adb shell "ps -A | grep face"
```

- 输出包含 `android.hardware.biometrics.face-service`：**PASS**
- 不包含：**FAIL**
- 无 adb 设备：**BLOCKED**

### 7. 人脸算法版本检查（开机 log）

**前置**：用户必须提供开机 log 路径；未提供则 **BLOCKED**。

在 log 中查找：

```text
face_algorithm_init st_version: <版本号>
```

- 找到且版本号非空：**PASS**，说明列写出完整版本字符串（如 `2.1.0.088.3.858-express-346a3fb`）。
- 未找到或 `ret` 非 0 导致无版本行：**FAIL** / 结合初始化项判断。

详细规则见 [CHECK_ITEMS.md](CHECK_ITEMS.md) 第 8～10 节。

---

## 指纹 / 人脸检查进度

```text
检查进度：
指纹：
- [ ] rc/xml、DTS、DWS、驱动、tran-keys
人脸（需 log 路径）：
- [ ] Face HAL 初始化（开机 log）
- [ ] 人脸服务（adb ps）
- [ ] 人脸算法版本（开机 log）
- [ ] 输出汇总表
```

---

## 三、固定输出格式（必须遵守）

默认输出**一张汇总表 + 总体结论 + 建议动作**，不写 3.x 分项长文。用户明确要求「详细说明」时，再补充对应检查项证据。

### 格式约束

- 结论仅允许：`PASS`、`FAIL`、`BLOCKED`（全大写）。
- 有风险但可继续调试：结论写 `PASS`，在「说明」列写 `风险：...`。
- 「说明」列每条 1～2 句话，写关键字段或差异即可，不贴大段日志。
- 全 PASS 且无风险时，「建议动作」写「无」。

### 报告模板（默认使用）

按用户请求输出**指纹表**和/或**人脸表**；未请求的检查块整段省略。

```markdown
## 生物识别调试项检查报告 - <项目代号>

**基础信息**：<平台/SoC> | kernel <版本> | 指纹 <IC/架构> | 人脸 log `<log路径或「未提供」>`

### 指纹

| 检查项 | 结论 | 说明 |
| --- | --- | --- |
| rc/xml | PASS / FAIL / BLOCKED | |
| fp_fw / project_info | PASS / FAIL / BLOCKED / 不适用 | |
| DTS GPIO | PASS / FAIL / BLOCKED | |
| DWS GPIO | PASS / FAIL / BLOCKED | |
| 驱动配置 | PASS / FAIL / BLOCKED | |
| tran-keys | PASS / FAIL / BLOCKED | |

### 人脸

| 检查项 | 结论 | 说明 |
| --- | --- | --- |
| Face HAL 初始化 | PASS / FAIL / BLOCKED | 关键 log：`Face HAL started`、`face_algorithm_init ret: 0` 等 |
| 人脸服务 | PASS / FAIL / BLOCKED | `ps -A \| grep face` 含 `android.hardware.biometrics.face-service` |
| 人脸算法版本 | PASS / FAIL / BLOCKED | `st_version: <版本号>` |

**总体结论**：可继续调试 / 需修复后复测 / 信息不足待补充

**建议动作**：
1. <仅列 FAIL、BLOCKED、风险项；全 PASS 写「无」>
```

### 仅检查单项时

仍用对应分表（指纹或人脸），只保留相关行 + 基础信息 + 总体结论 + 建议动作。

### 禁止的输出方式

- 禁止默认输出 3.1～3.6 多节长文、多张明细子表。
- 禁止同一项目混用「仅列表」「仅段落」替代汇总表。
- 禁止在说明列堆砌无关外设差异。
