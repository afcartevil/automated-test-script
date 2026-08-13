---
name: "tranprojects-upgrade"
description: "MTK Sensorhub 3.0 tranprojects 路径升级。将旧基线 tran_projects/device/transsion 下的 sensor 配置迁移到新基线 vendor/transsion/projects。Invoke when upgrading device-vext.mk, ProjectConfig.mk, or sensor_config.json for CLx/ODx projects."
funcType: "AI自动化适配"
category: "驱动"
---

# MTK Sensorhub 3.0 tranprojects 路径升级

## 概述

本 Skill 用于协助完成 MTK Sensorhub 3.0 平台从旧基线 `tran_projects` / `device/transsion` 路径到新基线 `vendor/transsion/projects` 路径的 sensor 配置迁移。

## 背景

- **榫卯4.0**：新基线（A14/A15/A16等）采用的新方案，减少软件复杂度、优化解耦组件化
- **路径变化**：代码从 `tran_projects/<project>/.../device/transsion/<project>/` 迁移到 `vendor/transsion/projects/<project>/`
- **核心变化**：原代码通过宏定义区分项目，升级后改为解析 DTS（设备树）的方式

## 参考文档

- [AI]底软集成sensor3.0 MTK平台P1-/vendor/transsion/projects：https://transsioner.feishu.cn/wiki/MJoywf93GiZSH4kqCmGcXHQTnSd
- [AI]底软集成sensor3.0 MTK平台P1-整体：https://transsioner.feishu.cn/wiki/DE6YwDyguirlqckJc2TcKxu7nCg
- 底软集成sensor3.0 MTK平台P1：https://transsioner.feishu.cn/wiki/V7Etwk5lRiMbFCkWCl0cBxcsnRg
- Sensor榫卯4.0Kernel侧改动介绍：https://transsioner.feishu.cn/docx/S2SEdBKTXoLIubxVSeRcZFVEnTb
- MTK Sensor HAL榫卯软件设计与应用指导：https://transsioner.feishu.cn/docx/DwF1dD9dfo9eiWxbSCfcqYVPnUg

## 涉及文件

| 文件 | 说明 |
|------|------|
| `vendor/transsion/projects/<project>/device-vext.mk` | XML权限声明 + 传感器属性值 + IRTX配置 |
| `vendor/transsion/projects/<project>/ProjectConfig.mk` | 项目端 sensor 宏配置，覆盖平台端 |
| `vendor/transsion/projects/<project>/sensor_config.json` | 新增：sensor HAL 配置文件（光感类型等） |

---

## 强制执行规则

### 规则 1：前置完整性检查（最高优先级）
**开始任何修改前，必须扫描以下所有路径，确保找到全部旧项目配置文件：**

| 搜索路径 | 目标文件 |
|----------|----------|
| `tran_projects/<project>/.../device/transsion/<project>/` | `ProjectConfig_overlay.mk` |
| `device/transsion/<project>/` | `device-vext.mk`、`ProjectConfig.mk` |
| `vendor/transsion/projects/<project>_old/.../` | `device-vext.mk` |

**检查逻辑**：
1. 逐个路径搜索，列出找到的文件及路径
2. 如 `ProjectConfig_overlay.mk` 未找到，向用户索要宏定义文件路径
3. 如 `device-vext.mk` 未找到，向用户索要属性值文件路径
4. 所有文件齐全后才能继续，**禁止在缺少任何配置文件时开始修改**

**输出示例**：
```
📋 完整性检查
├─ ProjectConfig_overlay.mk: ✅ tran_projects/x6850/.../ProjectConfig_overlay.mk
├─ device-vext.mk:           ✅ device/transsion/x6850_h895/device-vext.mk
└─ ProjectConfig.mk:         ⚠️ 未找到，请提供路径
```

### 规则 2：以旧项目为准
- 所有配置必须从旧项目源文件中读取
- 如果旧项目配置与文档示例不同，以旧项目为准
- 升级不会新增或减少 sensor，不修改硬件，不修改红外位置
- 新增或减少 feature 不在 tranproject 这里处理

### 规则 3：先提问，再全自动执行
- **先提问**：规则1中的前置检查完成后，如果存在路径缺失或信息不足，先向用户提问解决，不要猜测。
- **全自动执行**：信息完备后，AI 自动完成全部步骤，不再逐步确认。
- **完成后展示摘要**：全部改完后一次性展示修改摘要及具体变更内容。
- **仅在歧义时中断**：执行过程中只有遇到无法自主判断的内容（如光感类型不确定等）才向用户提问。

---

## 升级流程

### 步骤 1：前置完整性检查

#### 操作
1. **扫描 `tran_projects` 路径**：搜索 `tran_projects/<project>/.../device/transsion/<project>/ProjectConfig_overlay.mk`
2. **扫描 `device/transsion` 路径**：搜索 `device/transsion/<project>/device-vext.mk`
3. **生成完整性报告**：列出所有找到的配置文件及其路径
4. **确认缺失项**：如必要文件缺失，提示用户补充路径

#### 输出
```
📋 完整性检查报告
├─ 项目代号：<project>
├─ ProjectConfig_overlay.mk: [✅ 已找到 / ⚠️ 缺失]
├─ device-vext.mk:           [✅ 已找到 / ⚠️ 缺失]
└─ 结论：[可以继续 / 需要补充路径]
```

---

### 步骤 2：检索旧项目配置

#### 操作
读取旧项目的以下文件（来自步骤1确认的路径）：
- `device-vext.mk` — 传感器属性值、工模检测阈值、IRTX配置、光感属性
- `ProjectConfig_overlay.mk` — 传感器宏配置

#### 输出
分析旧项目 sensor 配置，列出：
- **物理传感器**：加速度、地磁、光感/距感、陀螺仪、SAR、OIS、气压计等
- **虚拟传感器**：计步器、静止检测、倾斜检测、重力、旋转矢量、游戏旋转矢量、线性加速度、方向、抬起手势、面朝下、设备朝向、运动检测、唤醒手势、大幅运动等
- **步态传感器**：步数计数器、步数检测器
- **非标定传感器**：非标定加速度、非标定陀螺仪、非标定地磁
- **红外**：是否有 IRTX 支持
- **光感类型**：狭缝光感（Screen）还是屏下光感（UnderScreen）
- **属性值**：工模检测阈值、SAR offset、红外配置、光感 ML 校准、Gamma 参数等

#### 光感类型判断

根据旧项目 `device-vext.mk` 中的属性判断光感类型：

| 特征属性 | 光感类型 |
|----------|----------|
| 无 `ro.vendor.tran.als.underscreen` 且无 `ro.vendor.tran.alscali.ml.screentype = UnderScreen` | 狭缝光感（Screen） |
| 有 `ro.vendor.tran.als.underscreen` 或 `ro.vendor.tran.alscali.ml.screentype = UnderScreen` | 屏下光感（UnderScreen） |

---

### 步骤 3：配置 device-vext.mk

#### XML 权限声明

**新旧格式对比**：

| 旧基线格式 | 新基线格式 |
|-----------|-----------|
| `PRODUCT_PACKAGES += android.hardware.sensor.xxx.prebuilt.xml` | `PRODUCT_COPY_FILES += frameworks/native/data/etc/android.hardware.sensor.xxx.xml:odm/etc/permissions/android.hardware.sensor.xxx.prebuilt.xml` |

**传感器 XML 对应关系**：

| 宏 | XML 文件名 |
|----|-----------|
| `CUSTOM_KERNEL_ACCELEROMETER` | `android.hardware.sensor.accelerometer` |
| `CUSTOM_KERNEL_MAGNETOMETER` | `android.hardware.sensor.compass` |
| `CUSTOM_KERNEL_ALSPS` | `android.hardware.sensor.proximity` + `android.hardware.sensor.light` |
| `CUSTOM_KERNEL_GYROSCOPE` | `android.hardware.sensor.gyroscope` |
| `CUSTOM_KERNEL_BAROMETER` | `android.hardware.sensor.barometer` |
| `CUSTOM_KERNEL_STEP_COUNTER` | `android.hardware.sensor.stepcounter` |
| `CUSTOM_KERNEL_STEP_DETECTOR` | `android.hardware.sensor.stepdetector` |
| `CUSTOM_HIFI_SENSORS` | `android.hardware.sensor.hifi_sensors` |
| `CUSTOM_KERNEL_HINGE_ANGLE` | `android.hardware.sensor.hinge_angle` |

#### 属性值

**关键变更**：
- `PRODUCT_PROPERTY_OVERRIDES` → `PRODUCT_ODM_PROPERTIES`（大部分属性）
- `PRODUCT_VENDOR_PROPERTIES` → `PRODUCT_ODM_PROPERTIES`
- 部分属性保留 `PRODUCT_PROPERTY_OVERRIDES`

##### 必须属性（所有项目都要）

```makefile
PRODUCT_PROPERTY_OVERRIDES += ro.vendor.tran.new_als_kvalue_nv = 1   # 校准数据存新nv
PRODUCT_ODM_PROPERTIES += ro.vendor.tran.sensor.rgt.devinfo = 1      # 工程模式查看硬件信息
```

> ⚠️ **注意**：`ro.vendor.tran.new_als_kvalue_nv` 保持使用 `PRODUCT_PROPERTY_OVERRIDES`，**不要**改为 `PRODUCT_ODM_PROPERTIES`。

##### 项目特有属性（从旧项目复制，将 `PRODUCT_PROPERTY_OVERRIDES` 改为 `PRODUCT_ODM_PROPERTIES`）

```makefile
PRODUCT_ODM_PROPERTIES += ro.vendor.tran.ir.led.back = 1  # 后置红外（如有）
```

##### 工模检测属性（从旧项目复制，将 `PRODUCT_PROPERTY_OVERRIDES` 改为 `PRODUCT_ODM_PROPERTIES`）

```makefile
PRODUCT_ODM_PROPERTIES += ro.vendor.tran.midtest.ps.noise.min = <值>
PRODUCT_ODM_PROPERTIES += ro.vendor.tran.midtest.ps.noise.max = <值>
PRODUCT_ODM_PROPERTIES += ro.vendor.tran.midtest.ps.diff5.min = <值>
PRODUCT_ODM_PROPERTIES += ro.vendor.tran.midtest.ps.diff5.max = <值>
PRODUCT_ODM_PROPERTIES += ro.vendor.tran.midtest.ps.cali.diff3 = <值>
PRODUCT_ODM_PROPERTIES += ro.vendor.tran.midtest.ps.diff3.max = <值>
PRODUCT_ODM_PROPERTIES += ro.vendor.tran.midtest.ls.factor.min = <值>
PRODUCT_ODM_PROPERTIES += ro.vendor.tran.midtest.ls.factor.max = <值>
PRODUCT_ODM_PROPERTIES += ro.vendor.tran.midtest.ls.0lux.max = <值>
```

##### 屏下光感 ML 校准属性（仅屏下光感项目，从旧项目复制）

```makefile
PRODUCT_ODM_PROPERTIES += ro.vendor.tran.single_light_sensor = 1
PRODUCT_ODM_PROPERTIES += ro.vendor.tran.alscali.ml = 1
PRODUCT_ODM_PROPERTIES += ro.vendor.tran.alscali.ml.screentype = UnderScreen
PRODUCT_ODM_PROPERTIES += ro.vendor.tran.alscali.ml.vendortype = <SensorTek/Eminent/...>
PRODUCT_ODM_PROPERTIES += ro.vendor.tran.alscali.ml.algotype = <Cutout/...>
PRODUCT_ODM_PROPERTIES += ro.vendor.tran.alscali.ml.version = <V1_0_0/...>
PRODUCT_ODM_PROPERTIES += ro.vendor.tran.alscali.readnv.version = 3
PRODUCT_ODM_PROPERTIES += ro.vendor.tran.als.screenrgb.check = 1
```

##### 光感 Gamma 参数（仅屏下光感项目，从旧项目复制）

```makefile
PRODUCT_ODM_PROPERTIES += ro.vendor.tran.midtest.ls.R2G2B2gamma.min = <值>
PRODUCT_ODM_PROPERTIES += ro.vendor.tran.midtest.ls.R2G2B2gamma.max = <值>
PRODUCT_ODM_PROPERTIES += ro.vendor.tran.midtest.ls.R3G3B3gamma.min = <值>
PRODUCT_ODM_PROPERTIES += ro.vendor.tran.midtest.ls.R3G3B3gamma.max = <值>
PRODUCT_ODM_PROPERTIES += ro.vendor.tran.midtest.ls.k.min = <值>
PRODUCT_ODM_PROPERTIES += ro.vendor.tran.midtest.ls.k.max = <值>
```

##### SAR 属性（如有 SAR sensor）

```makefile
PRODUCT_ODM_PROPERTIES += ro.vendor.tran.sar.far.offset.c0 = <值>
PRODUCT_ODM_PROPERTIES += ro.vendor.tran.sar.far.offset.c1 = <值>
# ... 等其他 SAR 属性
```

#### IRTX 配置

**原则：以旧项目为准，不强制新增模板**。旧项目 `device-vext.mk` 中有什么 IRTX 相关属性和 XML 声明就迁移什么，没有就不加。不要套用固定模板。

---

### 步骤 4：配置 ProjectConfig.mk

#### 新旧路径对比

| | 旧基线 | 新基线 |
|---|--------|--------|
| 路径 | `tran_projects/<project>/.../device/transsion/<project>/ProjectConfig_overlay.mk` | `vendor/transsion/projects/<project>/ProjectConfig.mk` |

#### 关键变更

| 旧宏名称 | 新宏名称 | 说明 |
|----------|----------|------|
| `MTK_IRTX_PWM_SUPPORT` | `TRAN_IR_SUPPORT` | 红外发射器支持 |

#### 配置原则

1. **以旧项目为准**：所有 macro 值和旧项目保持一致
2. **不新增 sensor**：升级不会新增或减少 sensor，不修改硬件，不修改红外位置
3. **不新增 feature**：新增或减少 feature 不在 tranproject 这里处理
4. **删除多余配置**：如果新基线中存在旧项目未配置的 macro，应该删除

#### 配置模板

```makefile
# sensor config
MTK_SENSOR_ARCHITECTURE = 2.0
CUSTOM_HAL_SENSORS = sensor
CUSTOM_HIFI_SENSORS = no

# 物理传感器
CUSTOM_KERNEL_ACCELEROMETER = <yes/no>
CUSTOM_KERNEL_ALSPS = <yes/no>
CUSTOM_KERNEL_ALSFLICKER_SENSOR = <yes/no>
TRAN_FLICKER_LID_SUPPORT = <yes/no>
CUSTOM_KERNEL_MAGNETOMETER = <yes/no>
CUSTOM_KERNEL_GYROSCOPE = <yes/no>
CUSTOM_KERNEL_BAROMETER = <yes/no>
CUSTOM_KERNEL_SAR_SENSOR = <yes/no>

# OIS（OIS 不由 sensor 负责，保持原样不修改）
CUSTOM_KERNEL_OIS_SENSOR = <yes/no>

# 虚拟传感器 — 标准
CUSTOM_KERNEL_STEP_COUNTER = <yes/no>
CUSTOM_KERNEL_STEP_DETECTOR = <yes/no>
CUSTOM_KERNEL_SIGNIFICANT_MOTION_SENSOR = <yes/no>
CUSTOM_KERNEL_WAKE_GESTURE_SENSOR = <yes/no>
CUSTOM_KERNEL_STATIONARY_SENSOR = <yes/no>
CUSTOM_KERNEL_TILT_DETECTOR_SENSOR = <yes/no>
VIRTUAL_GYROSCOPE_ALGORITHM = <yes/no>
# 虚拟传感器 — 动作类
CUSTOM_KERNEL_PICK_UP_SENSOR = <yes/no>
CUSTOM_KERNEL_FACE_DOWN_SENSOR = <yes/no>
CUSTOM_KERNEL_DEVICE_ORIENTATION = <yes/no>
CUSTOM_KERNEL_ACTIVITY_SENSOR = <yes/no>
CUSTOM_KERNEL_GLANCE_GESTURE_SENSOR = <yes/no>

# 虚拟传感器 — 矢量类
CUSTOM_KERNEL_GRAVITY_SENSOR = <yes/no>
CUSTOM_KERNEL_GRV_SENSOR = <yes/no>
CUSTOM_KERNEL_GMRV_SENSOR = <yes/no>
CUSTOM_KERNEL_LINEARACCEL_SENSOR = <yes/no>
CUSTOM_KERNEL_ORIENTATION_SENSOR = <yes/no>
CUSTOM_KERNEL_RV_SENSOR = <yes/no>

# 非标定
CUSTOM_KERNEL_UNCALI_ACC_SENSOR = <yes/no>
CUSTOM_KERNEL_UNCALI_GYRO_SENSOR = <yes/no>
CUSTOM_KERNEL_UNCALI_MAG_SENSOR = <yes/no>

# 防误触距感（如有）
CUSTOM_KERNEL_ANTI_TOUCH_PS_SENSOR = <yes/no>

# 红外
TRAN_IR_SUPPORT = <yes/no>

# 超声距感
MTK_ULTRASND_PROXIMITY = <yes/no>

# 屏下光感 ML 校准（仅屏下光感项目启用）
TRAN_AlsCali_ML = <yes/no>
TRAN_AlsCali_ML_ScreenType = <UnderScreen/NormalScreen>
TRAN_AlsCali_ML_VendorType = <SensorTek/Eminent/...>
TRAN_AlsCali_ML_AlgoType = <Cutout/...>
TRAN_AlsCali_ML_Version = <V1_0_0/...>

# 屏下光感 LID 支持（仅屏下光感项目启用）
TRAN_ALSNUMBER18BIT32_LID_SUPPORT = <yes/no>
TRAN_ALS_NUMBER27_BIT32_LID_SUPPORT = <yes/no>
```

#### 注意事项

- **不相关 sensor 设为 no（而不是删除）**：即使在旧项目中未出现的 sensor macro，如果新基线模板中有，保留并设为 `no`
- **旧项目存在但新基线没有的 macro**：不要新增，说明该 sensor 在新基线下可能通过其他方式配置
- **`GRV_SENSOR` vs `GRAVITY_SENSOR`**：`GRV_SENSOR` 是 2.0 arch 中 Gravity 的内部实现，`GRAVITY_SENSOR` 对应 AOSP 标准 Gravity sensor，两者独立配置

#### 超声距感宏处理规则

- **非超声距感项目**：必须将 `MTK_ULTRASND_PROXIMITY` 设为 `no`
  - 如何判断：检查旧项目 `ProjectConfig_overlay.mk` 中 `MTK_ULTRASND_PROXIMITY` 的值。注意旧项目中可能有多处定义，以**最后一次定义**的值为准（makefile 语法规则）
  - 如果新基线 `ProjectConfig.mk` 中没有 `MTK_ULTRASND_PROXIMITY` 这个宏，要手动加上并设为 `no`
- **超声距感项目**：保持 `MTK_ULTRASND_PROXIMITY = yes`

#### 狭缝光感 vs 屏下光感宏处理规则

根据步骤2判断的光感类型，在 `ProjectConfig.mk` 中处理以下宏：

| 宏 | 狭缝光感（Screen） | 屏下光感（UnderScreen） |
|----|-------------------|------------------------|
| `CUSTOM_KERNEL_ALSFLICKER_SENSOR` | `no` | 以旧项目为准 |
| `TRAN_FLICKER_LID_SUPPORT` | `no` | 以旧项目为准 |
| `TRAN_AlsCali_ML` | `no` | 以旧项目为准 |
| `TRAN_AlsCali_ML_ScreenType` | 删除或注释 | `UnderScreen`（以旧项目为准） |
| `TRAN_AlsCali_ML_VendorType` | 删除或注释 | 以旧项目为准 |
| `TRAN_AlsCali_ML_AlgoType` | 删除或注释 | 以旧项目为准 |
| `TRAN_AlsCali_ML_Version` | 删除或注释 | 以旧项目为准 |
| `TRAN_ALSNUMBER18BIT32_LID_SUPPORT` | `no` | 以旧项目为准 |
| `TRAN_ALS_NUMBER27_BIT32_LID_SUPPORT` | `no` | 以旧项目为准 |

> ⚠️ **注意**：狭缝光感项目如果新基线中没有上述屏下相关宏，需要手动添加并设为 `no`（或删除/注释 `TRAN_AlsCali_ML_*` 系列）。核心原则：狭缝光感不启用任何屏下光感的 feature。

---

### 步骤 5：配置 sensor_config.json

#### 概述
新增文件，用于 sensor HAL 的配置。根据步骤2中判断的光感类型选择模板。

#### 狭缝光感模板（Screen）

```json
{
    "tran_sensors": [
        {
            "type": "als_ml",
            "parameters": {
                "screentype": "Screen"
            }
        },
        {
            "type": "als_common",
            "parameters": {
                "readnv_version": 3
            }
        },
        {
            "type": "sample_type",
            "parameters": {
                "double_params": 0.1,
                "integer_params": 10,
                "string_params": "sample_code"
            }
        }
    ]
}
```

#### 屏下光感模板（UnderScreen）

```json
{
    "tran_sensors": [
        {
            "type": "als_ml",
            "parameters": {
                "screentype": "UnderScreen",
                "vendortype": "SensorTek",
                "algotype": "Cutout",
                "version": "1.0"
            }
        },
        {
            "type": "als_common",
            "parameters": {
                "readnv_version": 3
            }
        },
        {
            "type": "sample_type",
            "parameters": {
                "double_params": 0.1,
                "integer_params": 10,
                "string_params": "sample_code"
            }
        }
    ]
}
```

> ⚠️ **注意**：屏下光感模板中的 `vendortype` 和 `algotype` 应根据实际光感传感器型号确定，模板中的 `"SensorTek"` 和 `"Cutout"` 仅为示例值。***优先从旧项目 `device-vext.mk` 中的 `ro.vendor.tran.alscali.ml.vendortype` 和 `ro.vendor.tran.alscali.ml.algotype` 获取。***

#### 补充说明

- 如果项目 `device-vext.mk` 中定义了 sensor xml 的 `PRODUCT_COPY_FILES`，需要同步添加
- 如果项目是狭缝光感，`screentype` 设为 `"Screen"` 即可
- `readnv_version` 默认设为 3
- `sample_type` 为保留的默认配置，不要修改
- 光感类型判断参见步骤2

---

## 常见陷阱

### 1. 属性类型混淆
- **问题**：错误地将 `ro.vendor.tran.new_als_kvalue_nv` 从 `PRODUCT_PROPERTY_OVERRIDES` 改为 `PRODUCT_ODM_PROPERTIES`
- **解决**：`ro.vendor.tran.new_als_kvalue_nv` 必须保持 `PRODUCT_PROPERTY_OVERRIDES`

### 2. 多余的 sensor macro
- **问题**：新基线 ProjectConfig.mk 中存在旧项目未配置的 sensor macro（如 OIS、气压计等）
- **解决**：旧项目不存在或设为 `no` 的 macro，在新基线中也应设为 `no` 或删除

### 3. IRTX 配置未遵循旧项目
- **问题**：套用固定 IRTX 模板，新增了老项目没有的属性或 XML
- **解决**：以旧项目 `device-vext.mk` 为准，旧项目有什么就迁移什么，没有就不加

### 4. 旧宏名未更新
- **问题**：ProjectConfig.mk 中仍使用 `MTK_IRTX_PWM_SUPPORT` 而非 `TRAN_IR_SUPPORT`
- **解决**：全局搜索替换，确保使用新宏名

### 5. 狭缝光感项目未关闭屏下宏
- **问题**：狭缝光感项目（Screen）的 `ProjectConfig.mk` 中仍然启用了屏下光感相关宏（`CUSTOM_KERNEL_ALSFLICKER_SENSOR`、`TRAN_FLICKER_LID_SUPPORT`、`TRAN_AlsCali_ML` 系列等）
- **解决**：根据光感类型，狭缝光感项目必须将上述宏全部设为 `no` 或删除/注释

### 6. 非超声距感项目未关闭超声宏
- **问题**：非超声距感项目的 `ProjectConfig.mk` 中 `MTK_ULTRASND_PROXIMITY` 未明确设为 `no`，或文件中缺少此宏
- **解决**：非超声距感项目必须确保 `MTK_ULTRASND_PROXIMITY = no`，若文件中不存在此宏则手动添加

### 7. 路径检索不完整（🆕）
- **问题**：只搜索 `tran_projects` 路径，遗漏了 `device/transsion` 或 `vendor/transsion/projects` 路径下的 `device-vext.mk`
- **解决**：严格遵循规则1的前置完整性检查，确保两个核心配置文件都已找到

### 8. 属性值遗漏（🆕）
- **问题**：只迁移了工模检测基础属性（ps/ls 阈值），遗漏了屏下光感 ML 校准属性（`alscali.ml.*`）和光感 Gamma 参数（`ls.R2G2B2gamma.*`、`ls.k.*` 等）
- **解决**：完整读取旧项目 `device-vext.mk` 中所有 sensor 相关属性，逐项确认是否已迁移

---

## 验证清单

- [ ] **前置检查**：确认 ProjectConfig_overlay.mk 和 device-vext.mk 都已找到
- [ ] `device-vext.mk` XML 声明从 `PRODUCT_PACKAGES` 改为 `PRODUCT_COPY_FILES`（路径：`odm/etc/permissions/`）
- [ ] `device-vext.mk` 属性从 `PRODUCT_PROPERTY_OVERRIDES` 改为 `PRODUCT_ODM_PROPERTIES`
- [ ] `device-vext.mk` 必须属性 `ro.vendor.tran.new_als_kvalue_nv = 1` 已添加（注意：保持 `PRODUCT_PROPERTY_OVERRIDES`）
- [ ] `device-vext.mk` 必须属性 `ro.vendor.tran.sensor.rgt.devinfo = 1` 已添加
- [ ] `device-vext.mk` 工模检测属性（ps/ls 阈值）已从旧项目完整迁移
- [ ] `device-vext.mk` 屏下光感 ML 校准属性已从旧项目完整迁移（如适用）
- [ ] `device-vext.mk` 光感 Gamma 参数已从旧项目完整迁移（如适用）
- [ ] `device-vext.mk` IRTX 属性与旧项目一致（不额外新增，不遗漏）
- [ ] `ProjectConfig.mk` 旧宏 `MTK_IRTX_PWM_SUPPORT` 已改为 `TRAN_IR_SUPPORT`
- [ ] `ProjectConfig.mk` sensor 宏与旧项目一致（不新增、不删除 sensor）
- [ ] `ProjectConfig.mk` 旧项目未配置的 sensor macro 已设为 `no` 或删除
- [ ] `ProjectConfig.mk` 非超声距感项目：`MTK_ULTRASND_PROXIMITY = no`（若文件中不存在此宏，已手动添加）
- [ ] `ProjectConfig.mk` 狭缝光感项目：屏下相关宏（`CUSTOM_KERNEL_ALSFLICKER_SENSOR`、`TRAN_FLICKER_LID_SUPPORT`、`TRAN_AlsCali_ML` 系列、`TRAN_ALSNUMBER18BIT32_LID_SUPPORT`、`TRAN_ALS_NUMBER27_BIT32_LID_SUPPORT`）已全部设为 `no` 或删除/注释
- [ ] `sensor_config.json` 已创建，光感类型正确（狭缝：`"Screen"` / 屏下：`"UnderScreen"`）
- [ ] `sensor_config.json` 中 `readnv_version` 设为 3

---

## 自检规则

每次使用本 Skill 执行完升级操作后，AI 必须逐项自检以下 5 点：

1. **是否完成了用户要求的任务**
   - device-vext.mk、ProjectConfig.mk、sensor_config.json 三个文件是否都已正确修改？

2. **所有配置是否以旧项目为准**
   - 确认没有套用固定模板、没有自行假设属性值

3. **属性值是否完整迁移（🆕）**
   - 确认工模检测属性、屏下光感 ML 校准属性、Gamma 参数均已从旧项目完整迁移
   - 逐一比对旧项目 `device-vext.mk` 中所有 sensor 相关属性在新文件中是否存在

4. **是否存在不确定的内容**
   - 如果有无法确定的内容，必须明确说出"不确定"并说明原因

5. **IRTX 等属性是否正确**
   - 确认没有额外新增旧项目不存在的属性
   - 确认没有遗漏旧项目的配置

自检完成后，向用户输出自检结果摘要。
