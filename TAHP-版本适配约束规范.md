# TAHP 版本适配约束规范

> **版本**: v1.0 | **日期**: 2026-05-18 | **适用范围**: 适配引擎（version_adaptation + carrier_porting）
> **状态**: Approved
> **前置文档**: [TAHP-约束文件编写规范](TAHP-约束文件编写规范.md)

---

## 1. 概述

### 1.1 定位

本规范是 TAHP 适配引擎的**约束文件编写标准**，覆盖两大适配场景：

| 场景 | Domain 标识 | 对应引擎 |
|------|------------|---------|
| 大版本升级适配（Android N → N+1） | `version_adaptation` | 适配引擎 |
| Feature 特性移植（跨平台/跨版本） | `version_adaptation` (子类型) | 适配引擎 |
| 运营商需求移植 | `carrier_porting` | 适配引擎 |
| 共性问题处理（安全补丁/合规） | `version_adaptation` (子类型) | 适配引擎 |

### 1.2 与现有适配流程的关系

**本规范不替代现有流程，而是优化现有流程。**

```
现有流程（已验证可行）:
  Owner → [梳理完整SOP（3-7天）] → [转成Skill] → [AI执行适配]
                ↑ 整个 SOP 编写过程人工完成

TAHP 优化后:
  Owner → [填写约束条件（1-2小时）] → [系统自动生成Skill] → [AI执行适配] → [自动进化]
                ↑ 只需描述约束，系统生成执行逻辑
```

### 1.3 核心设计原则

| # | 原则 | 说明 |
|---|------|------|
| 1 | **约束驱动** | Owner 只需描述"是什么"和"不能做什么"，不描述"怎么做" |
| 2 | **规则库复用** | API 迁移规则通过 `shared/api-migration-rules/` 跨版本积累复用 |
| 3 | **策略分层** | 全自动 / 半自动 / 人工 三级策略，避免一刀切 |
| 4 | **门禁硬性** | 编译 100% 通过 + 回归 ≥ 95% 是硬性门禁，不可跳过 |
| 5 | **可验证** | 每条约束必须可自动化检验，不可验证的约束不计入门禁 |
| 6 | **版本化** | 所有约束文件通过 Git 管理，适配经验可追溯 |

---

## 2. 适配场景分类

### 2.1 四大适配场景

| 场景 | 触发时机 | 特点 | 约束文件 | 典型工作量 |
|------|---------|------|---------|-----------|
| **大版本升级适配** | Android N → N+1 发布 | 批量、可预测、有 AOSP Diff 参考 | `version-adaptation.yaml` | 持续 2-3 个月 |
| **Feature 特性移植** | 自研 Feature 迁移到新平台/新版本 | 依赖链长、需兼容性映射 | `version-adaptation.yaml`（type=feature） | 单 Feature 1-2 周 |
| **运营商需求移植** | 运营商定制需求跨项目迁移 | 需求文档→代码映射、合规检查 | `carrier-porting.yaml` | 单运营商 3-5 天 |
| **共性问题处理** | 安全补丁、合规修复 | 跨模块同步、模式统一 | `version-adaptation.yaml`（type=common） | 单补丁 1-2 天 |

### 2.2 约束文件选择指南

```
你的场景是什么？
├── Android 大版本升级（A15→A16, A16→A17...）
│   └── 使用 version-adaptation.yaml（默认）
│
├── 自研 Feature 移植到新平台/新版本
│   └── 使用 version-adaptation.yaml（type: feature_porting）
│
├── 运营商定制需求移植（Airtel/Vodafone/MTN...）
│   └── 使用 carrier-porting.yaml
│
└── 安全补丁/合规修复批量同步
    └── 使用 version-adaptation.yaml（type: common_issue）
```

---

## 3. version-adaptation.yaml 约束规范

### 3.1 完整 YAML Schema

```yaml
# ══════════════════════════════════════════════════════════════
# version-adaptation.yaml — 版本升级/特性移植/共性问题约束文件
# ══════════════════════════════════════════════════════════════

# ===== 模块元信息（必填） =====
module:
  name: string                    # 模块唯一标识符（kebab-case），如 telephony
  display_name: string            # 中文显示名，如 "通信模块"
  domain: "version_adaptation"    # 固定值
  owner: string                   # 负责人工号或邮箱
  team: string                    # 所属团队
  version: string                 # 约束文件版本号（semver）
  created: "YYYY-MM-DD"           # 创建日期
  updated: "YYYY-MM-DD"           # 最后更新日期

# ===== 适配类型（必填） =====
adaptation_type:
  type: enum                      # version_upgrade | feature_porting | common_issue
  # version_upgrade: 大版本升级（默认）
  # feature_porting: Feature特性移植
  # common_issue: 共性问题处理

# ===== 版本信息（version_upgrade 必填，其他可选） =====
version_info:
  source_version: string          # 源版本，如 "android-15.0.0_r1"
  target_version: string          # 目标版本，如 "android-16.0.0_r1"
  # 注意：版本标识必须使用 AOSP 官方 tag 格式

# ===== Feature 信息（feature_porting 必填） =====
feature_info:                     # 仅 type=feature_porting 时填写
  feature_name: string            # Feature 名称，如 "dual-sim-enhancement"
  source_project: string          # 来源项目，如 "cannon"
  target_project: string          # 目标项目，如 "meteor"
  description: string             # Feature 简要描述
  source_code_paths:              # Feature 源码路径列表
    - string

# ===== 共性问题信息（common_issue 必填） =====
common_issue_info:                # 仅 type=common_issue 时填写
  issue_id: string                # 补丁/问题 ID，如 "ASB-2026-05-01"
  issue_title: string             # 问题标题
  affected_modules:               # 受影响模块列表
    - string
  source_patch: string            # 补丁来源路径（如有）

# ===== 信息边界（必填） =====
context:
  codebase_paths:                 # 模块涉及的代码路径（必须完整）
    - string                      # 如 frameworks/opt/telephony/
  build_targets:                  # 编译目标列表
    - string                      # 如 TeleService, TelephonyProvider
  test_targets:                   # 测试目标列表
    - string                      # 如 android.telephony.cts
  dependency_modules:             # 依赖的其他模块（可能受影响）
    - string
  excluded_paths:                 # 明确排除的路径（不参与适配）
    - string

# ===== API 迁移规则引用（推荐填写） =====
api_migration_rules:
  # 方式一：内联规则（少量时使用）
  inline_rules:
    - old_api: string             # 旧 API 完整签名
      new_api: string             # 新 API 完整签名
      change_type: enum           # method_signature | method_rename | constant_moved |
                                  # class_relocated | interface_changed | deprecated_removed
      auto: boolean               # 是否可全自动迁移
      confidence: float           # 置信度（0.0-1.0），> 0.95 才全自动
      note: string                # 补充说明
      applicable_versions:        # 适用版本范围（可选）
        from: string
        to: string

  # 方式二：引用共享规则库（推荐）
  shared_rule_files:
    - "shared/api-migration-rules/telephony-migration.yaml"
    - "shared/api-migration-rules/framework-migration.yaml"

# ===== 适配约束红线（必填，至少3条） =====
adaptation_constraints:
  - string                        # 每条约束为一个明确的、可验证的声明
  # 示例:
  # - "不能因为适配而删除传音自研的业务逻辑"
  # - "新增的 Android 16 API 调用必须有 @RequiresApi(16) 注解"
  # - "HIDL/AIDL 接口变更必须同步更新接口定义和实现"
  # - "废弃 API 的迁移必须检查所有调用点，不能遗漏"
  # - "不能引入新的编译警告"

# ===== 适配排除规则（可选） =====
exclusion_rules:
  paths:                          # 排除的文件/目录模式
    - string                      # 如 "vendor/mediatek/proprietary/**"
  api_patterns:                   # 排除的 API 模式
    - string                      # 如 "com.mediatek.internal.*"
  reasons:                        # 排除原因
    - string

# ===== 适配策略偏好（可选，有默认值） =====
strategy_preferences:
  auto_confidence_threshold: 0.95 # 全自动置信度阈值（默认 0.95）
  semi_auto_min_confidence: 0.70  # 半自动最低置信度（默认 0.70）
  batch_size: 50                  # 批量处理大小（默认 50）
  parallel_agents: 4              # 并行 Agent 数量（默认 4）

# ===== 验收标准（必填） =====
acceptance_criteria:
  compile_pass: boolean           # 必须 true（硬性门禁）
  smoke_test_targets:             # 冒烟测试目标列表
    - string
  regression_targets:             # 功能回归测试列表
    - string
  regression_pass_rate: float     # 回归通过率阈值（推荐 ≥ 0.95）
  custom_checks:                  # 自定义检查项（可选）
    - name: string
      command: string             # 检查命令
      expected: string            # 期望输出

# ===== 评估数据集（推荐填写） =====
eval_dataset:
  path: string                    # 上一次适配记录的目录路径
  description: string             # 数据集说明
  # 目录结构:
  # eval-data/telephony-a15-to-a16/
  # ├── cases/
  # │   ├── case-001-api-migration.yaml
  # │   ├── case-002-behavior-change.yaml
  # │   └── case-003-deprecated-api.yaml
  # └── expected/
  #     ├── case-001-expected.json
  #     ├── case-002-expected.json
  #     └── case-003-expected.json
```

### 3.2 必填项速查表

| 字段 | 必填 | 版本升级 | Feature移植 | 共性问题 | 说明 |
|------|------|---------|------------|---------|------|
| `module` | **必填** | ✅ | ✅ | ✅ | |
| `adaptation_type` | **必填** | ✅ | ✅ | ✅ | |
| `version_info` | 条件必填 | ✅ | 可选 | 可选 | Feature移植时选填 |
| `feature_info` | 条件必填 | ❌ | ✅ | ❌ | |
| `common_issue_info` | 条件必填 | ❌ | ❌ | ✅ | |
| `context` | **必填** | ✅ | ✅ | ✅ | |
| `api_migration_rules` | 推荐 | ✅ | ✅ | ❌ | 可引用共享规则库 |
| `adaptation_constraints` | **必填** | ✅ (≥3条) | ✅ (≥3条) | ✅ (≥2条) | |
| `exclusion_rules` | 可选 | ✅ | ✅ | ❌ | |
| `strategy_preferences` | 可选 | ✅ | ❌ | ❌ | 有默认值 |
| `acceptance_criteria` | **必填** | ✅ | ✅ | ✅ | |
| `eval_dataset` | 推荐 | ✅ | ✅ | ❌ | |

### 3.3 完整示例：通信模块大版本升级

```yaml
# constraints/telephony/version-adaptation.yaml
module:
  name: telephony
  display_name: "通信模块"
  domain: "version_adaptation"
  owner: zhangsan
  team: comm-integration
  version: "1.0"
  created: "2026-05-18"
  updated: "2026-05-18"

adaptation_type:
  type: version_upgrade

version_info:
  source_version: "android-15.0.0_r1"
  target_version: "android-16.0.0_r1"

context:
  codebase_paths:
    - "frameworks/opt/telephony/"
    - "frameworks/base/telephony/"
    - "packages/services/Telephony/"
    - "frameworks/base/core/java/android/telephony/"
  build_targets:
    - "TeleService"
    - "TelephonyProvider"
    - "Telecom"
  test_targets:
    - "android.telephony.cts"
    - "com.android.phone.tests"
    - "com.android.server.telecom.tests"
  dependency_modules:
    - "framework"
    - "connectivity"
    - "media"
  excluded_paths:
    - "vendor/mediatek/proprietary/**"
    - "device/*/ril/**"

api_migration_rules:
  shared_rule_files:
    - "shared/api-migration-rules/telephony-migration.yaml"
    - "shared/api-migration-rules/framework-migration.yaml"
  inline_rules:
    - old_api: "TelephonyManager.getDataNetworkType()"
      new_api: "TelephonyManager.getServiceState().getDataNetworkType()"
      change_type: "method_signature"
      auto: true
      confidence: 0.98
      note: "Android 16 将 getDataNetworkType() 标记为 @Deprecated"

    - old_api: "PhoneFactory.getPhones()"
      new_api: "PhoneFactory.getPhoneList()"
      change_type: "method_rename"
      auto: true
      confidence: 0.92
      note: "返回类型从 Phone[] 改为 List<Phone>"

    - old_api: "IccCardConstants.INTENT_VALUE_ICC_ABSENT"
      new_api: "TelephonyManager.SIM_STATE_ABSENT"
      change_type: "constant_moved"
      auto: false
      confidence: 0.75
      note: "常量从 IccCardConstants 迁移到 TelephonyManager，需要检查上下文"

    - old_api: "ServiceState.getState()"
      new_api: "ServiceState.getVoiceRegState()"
      change_type: "method_rename"
      auto: true
      confidence: 0.88
      note: "区分语音注册状态和数据注册状态"

adaptation_constraints:
  - "不能因为适配而删除传音自研的业务逻辑"
  - "新增的 Android 16 API 调用必须有 @RequiresApi(VERSION_CODES.VANILLA_ICE_CREAM) 注解"
  - "HIDL/AIDL 接口变更必须同步更新接口定义文件和实现类"
  - "废弃 API 的迁移必须检查所有调用点（grep确认零残留），不能遗漏"
  - "不能引入新的编译警告（-Werror 编译通过）"
  - "PhoneInternalInterface 的回调方法签名变更必须同步更新所有实现类"
  - "RILJ/RILC 接口变更需要同时确认 Modem 固件兼容性"

exclusion_rules:
  paths:
    - "vendor/mediatek/proprietary/**"
    - "device/*/ril/**"
  api_patterns:
    - "com.mediatek.internal.*"
  reasons:
    - "MTK proprietary 代码不参与 AOSP 适配，由 MTK BSP 团队独立适配"
    - "Device 层 RIL 接口由芯片平台团队负责"

strategy_preferences:
  auto_confidence_threshold: 0.95
  semi_auto_min_confidence: 0.70
  batch_size: 50
  parallel_agents: 4

acceptance_criteria:
  compile_pass: true
  smoke_test_targets:
    - "call_functional_smoke"
    - "sms_functional_smoke"
    - "data_connection_smoke"
    - "sim_hot_swap_smoke"
  regression_targets:
    - "call_functional_test"
    - "sms_functional_test"
    - "data_connection_test"
    - "sim_hot_swap_test"
    - "volte_functional_test"
    - "vonr_functional_test"
  regression_pass_rate: 0.95
  custom_checks:
    - name: "无废弃API残留"
      command: "grep -rn 'getDataNetworkType()' frameworks/opt/telephony/ | grep -v '@Deprecated'"
      expected: "(空输出，无匹配)"

eval_dataset:
  path: "eval-data/telephony-a15-to-a16/"
  description: "A15→A16 适配过程中的典型案例，包含 API 迁移、行为变更、废弃API替换等"
```

---

## 4. carrier-porting.yaml 约束规范

### 4.1 YAML Schema

```yaml
# ══════════════════════════════════════════════════════════════
# carrier-porting.yaml — 运营商需求移植约束文件
# ══════════════════════════════════════════════════════════════

# ===== 模块元信息（必填） =====
module:
  name: string
  display_name: string
  domain: "carrier_porting"       # 固定值
  owner: string
  team: string
  version: string
  created: "YYYY-MM-DD"
  updated: "YYYY-MM-DD"

# ===== 运营商信息（必填） =====
carrier_info:
  source_project: string          # 源项目，如 "generic"
  target_carrier: string          # 目标运营商标识，如 "airtel-india"
  carrier_display_name: string    # 运营商显示名，如 "Airtel India"
  target_region: enum             # india | africa | southeast_asia | middle_east | latin_america

# ===== 信息边界（必填） =====
context:
  codebase_paths:
    - string
  build_targets:
    - string
  test_targets:
    - string
  dependency_modules:
    - string

# ===== 运营商定制需求清单（必填，至少1项） =====
carrier_specifics:
  - requirement: string           # 需求描述
    requirement_id: string        # 需求 ID（如有）
    code_paths:                   # 涉及的代码路径
      - string
    config_changes:               # 需要变更的配置文件
      - string
    overlay_files:                # Carrier overlay 文件
      - string
    auto: boolean                 # 是否可自动移植
    confidence: float             # 置信度
    note: string                  # 补充说明
    dependencies:                 # 依赖的其他需求项
      - string

# ===== 合规标准（必填） =====
compliance_standards:
  - string                        # 如 "GCF CCv3", "Airtel India RFI requirements v3.2"

# ===== 适配约束红线（必填，至少3条） =====
adaptation_constraints:
  - string

# ===== 验收标准（必填） =====
acceptance_criteria:
  compile_pass: boolean
  carrier_certification:          # 运营商认证测试项
    - string
  regression_targets:             # 回归测试目标（必须包含 generic）
    - string
  regression_pass_rate: float

# ===== 评估数据集（可选） =====
eval_dataset:
  path: string
  description: string
```

### 4.2 必填项速查表

| 字段 | 必填 | 说明 |
|------|------|------|
| `module` | **必填** | |
| `carrier_info` | **必填** | 源项目、目标运营商、区域 |
| `context` | **必填** | |
| `carrier_specifics` | **必填** | 至少 1 项需求 |
| `compliance_standards` | **必填** | 至少 1 项标准 |
| `adaptation_constraints` | **必填** | 至少 3 条 |
| `acceptance_criteria` | **必填** | |

### 4.3 完整示例：Airtel 印度运营商移植

```yaml
# constraints/telephony/carrier-porting.yaml
module:
  name: telephony
  display_name: "通信模块"
  domain: "carrier_porting"
  owner: zhangsan
  team: comm-integration
  version: "1.0"
  created: "2026-05-18"
  updated: "2026-05-18"

carrier_info:
  source_project: "generic"
  target_carrier: "airtel-india"
  carrier_display_name: "Airtel India"
  target_region: "india"

context:
  codebase_paths:
    - "frameworks/opt/telephony/"
    - "packages/services/Telephony/"
    - "vendor/mediatek/proprietary/packages/telephony/"
  build_targets:
    - "TeleService"
    - "TelephonyProvider"
  test_targets:
    - "android.telephony.cts"
    - "com.android.phone.tests"
  dependency_modules:
    - "framework"
    - "settings"

carrier_specifics:
  - requirement: "VoWiFi 预置支持"
    requirement_id: "AIRTEL-REQ-001"
    code_paths:
      - "frameworks/opt/telephony/src/java/com/mediatek/ims/vowifi/"
    config_changes:
      - "carrier_config_airtel.xml"
    overlay_files:
      - "packages/services/Telephony/res/xml/airtel_vowifi_config.xml"
    auto: true
    confidence: 0.90
    note: "基于 Android 标准 Wi-Fi Calling 框架，通过 CarrierConfigManager 配置"
    dependencies: []

  - requirement: "Airtel 分钟提醒"
    requirement_id: "AIRTEL-REQ-002"
    code_paths:
      - "packages/services/Telephony/src/com/android/phone/callsettings/"
    config_changes:
      - "call_feature_airtel.xml"
    overlay_files:
      - "packages/services/Telephony/res/values/airtel_strings.xml"
    auto: true
    confidence: 0.85
    note: "通过 InCallService 扩展实现，需要配置提醒间隔"
    dependencies: []

  - requirement: "Airtel USSD 定制"
    requirement_id: "AIRTEL-REQ-003"
    code_paths:
      - "frameworks/base/telephony/java/android/telephony/USSD.java"
    config_changes: []
    overlay_files: []
    auto: false
    confidence: 0.60
    note: "涉及 Modem AT 命令定制，需要确认芯片平台差异，建议人工处理"
    dependencies: ["AIRTEL-REQ-001"]

  - requirement: "Airtel SIM Toolkit 增强"
    requirement_id: "AIRTEL-REQ-004"
    code_paths:
      - "packages/apps/Stk/"
      - "frameworks/base/telephony/java/com/android/internal/telephony/uicc/"
    config_changes:
      - "stk_config_airtel.xml"
    overlay_files: []
    auto: true
    confidence: 0.80
    note: "标准 STK 框架扩展，主要配置变更"
    dependencies: []

compliance_standards:
  - "GCF CCv3"
  - "Airtel India RFI requirements v3.2"
  - "India Telecom Regulatory Authority (TRAI) DND compliance"

adaptation_constraints:
  - "运营商定制不能影响 generic 基础功能（必须通过 generic_functional_test 回归）"
  - "Carrier overlay 必须通过 Android 标准机制（CarrierConfigManager / Runtime Resource Overlay）"
  - "网络配置变更必须通过 AT 命令验证（Modem 侧确认）"
  - "不能硬编码运营商参数（APN/MCCMNC/号码格式），必须通过 carrier_config 管理"
  - "USSD / STK 定制必须通过标准 Android 框架扩展，不允许直接修改 Framework 基础类"
  - "所有运营商定制代码必须有 `// CARRIER: airtel-india` 注释标记，方便后续维护"

acceptance_criteria:
  compile_pass: true
  carrier_certification:
    - "GCF 基础认证测试通过"
    - "Airtel RFI 需求项全覆盖"
    - "TRAI DND 合规检查通过"
  regression_targets:
    - "generic_functional_test"       # 确保 generic 不受影响
    - "airtel_vowifi_test"
    - "airtel_call_settings_test"
    - "airtel_ussd_test"
    - "airtel_stk_test"
  regression_pass_rate: 0.95
```

---

## 5. API 迁移规则库规范

### 5.1 定位

API 迁移规则库是适配引擎**跨版本复用的核心资产**。每次版本升级积累的迁移规则，直接复用于下一次升级。

### 5.2 存储结构

```
constraints/shared/api-migration-rules/
├── README.md                       # 规则库说明和索引
├── telephony-migration.yaml        # 通信模块迁移规则
├── framework-migration.yaml        # Framework 层迁移规则
├── hal-migration.yaml              # HAL 层迁移规则
├── kernel-migration.yaml           # 内核接口迁移规则
├── media-migration.yaml            # 多媒体迁移规则
├── connectivity-migration.yaml     # 连接性迁移规则
└── power-migration.yaml            # 功耗管理迁移规则
```

### 5.3 规则文件格式

```yaml
# constraints/shared/api-migration-rules/telephony-migration.yaml
# API 迁移规则库 — 通信模块
# 版本: 1.0
# 最后更新: 2026-05-18
# 适用范围: Android Telephony Framework

metadata:
  module: "telephony"
  maintainers: ["zhangsan"]
  last_update: "2026-05-18"
  total_rules: 0  # 由系统自动维护

rules:
  # ===== API 变更规则 =====
  - id: "TEL-001"
    old_api: "TelephonyManager.getDataNetworkType()"
    new_api: "TelephonyManager.getServiceState().getDataNetworkType()"
    change_type: "method_signature"
    introduced_in: "android-16.0.0_r1"    # 从哪个版本开始变更
    deprecated_in: "android-15.0.0_r1"    # 从哪个版本开始废弃
    auto: true
    confidence: 0.98
    scope: "framework"                     # framework | hal | kernel
    affected_files_pattern: "**/telephony/**/*.java"
    migration_steps:                       # 自动迁移步骤（可选，供 AI 参考）
      - "查找所有 getDataNetworkType() 调用点"
      - "替换为 getServiceState().getDataNetworkType()"
      - "添加 null check（getServiceState() 可能返回 null）"
      - "更新相关 import 语句"
    verified_in:                           # 已验证通过的版本
      - "android-16.0.0_r1"
    note: "Android 16 将 getDataNetworkType() 标记为 @Deprecated"

  - id: "TEL-002"
    old_api: "PhoneFactory.getPhones()"
    new_api: "PhoneFactory.getPhoneList()"
    change_type: "method_rename"
    introduced_in: "android-16.0.0_r1"
    auto: true
    confidence: 0.92
    scope: "framework"
    affected_files_pattern: "**/telephony/**/*.java"
    migration_steps:
      - "将 getPhones() 替换为 getPhoneList()"
      - "返回类型从 Phone[] 改为 List<Phone>，需要调整下游代码"
      - "检查是否有 .length 调用需要改为 .size()"
    verified_in:
      - "android-16.0.0_r1"
    note: "返回类型从 Phone[] 改为 List<Phone>"

  - id: "TEL-003"
    old_api: "IccCardConstants.INTENT_VALUE_ICC_ABSENT"
    new_api: "TelephonyManager.SIM_STATE_ABSENT"
    change_type: "constant_moved"
    introduced_in: "android-16.0.0_r1"
    auto: false
    confidence: 0.75
    scope: "framework"
    affected_files_pattern: "**/telephony/**/*.java"
    migration_steps:
      - "查找所有 IccCardConstants.INTENT_VALUE_ICC_ABSENT 引用"
      - "评估上下文：是否可以直接替换"
      - "有些场景 IccCardConstants 和 TelephonyManager 的语义可能不同"
    verified_in: []
    note: "常量从 IccCardConstants 迁移到 TelephonyManager，需要检查上下文语义"
```

### 5.4 规则积累机制

```
版本升级适配过程中的规则积累流程:

  1. AOSP Diff 分析
     ↓ 提取 API/接口/行为变更清单
  2. 代码影响扫描
     ↓ 定位受影响的定制代码
  3. 适配执行
     ↓ 全自动/半自动/人工
  4. 成功适配经验提取 ← 关键步骤
     ↓ 将成功的适配模式写入规则库
  5. 规则入库
     ↓ 含置信度、适用版本范围、迁移步骤
  6. 下次升级时复用
     ↓ 规则库 + 新增 AOSP Diff → 自动匹配

预期效果（基于通信模块估算）:
  A15→A16 (首次):  全自动 40% | 半自动 40% | 人工 20%
  A16→A17 (积累1次): 全自动 60% | 半自动 30% | 人工 10%
  A17→A18 (积累2次): 全自动 75% | 半自动 20% | 人工  5%
```

### 5.5 规则质量标准

| 指标 | 标准 | 说明 |
|------|------|------|
| 规则 ID 唯一性 | 必须唯一 | 格式: `{MODULE_PREFIX}-{NUMBER}`，如 TEL-001 |
| 置信度准确性 | 与实际成功率偏差 ≤ 10% | 如果标注 0.95 但实际成功率 < 0.85，需要下调 |
| 迁移步骤可复现 | 按步骤执行可以独立完成迁移 | 不能有模糊描述 |
| 版本范围准确 | `introduced_in` 必须与 AOSP tag 对应 | 使用官方 tag 格式 |
| 验证状态 | `verified_in` 记录实际验证通过的版本 | 未验证的规则 confidence 自动降 0.1 |

---

## 6. 适配策略分类标准

### 6.1 三级策略

| 策略 | 判定条件 | 处理方式 | 审核要求 | 产出 |
|------|---------|---------|---------|------|
| 🟢 **全自动** | 已知迁移模式 + API 规则匹配 + 置信度 > 95% | 自动生成 patch → 编译验证 → 回归测试 | 系统自动审核 | 合格 patch 直接合入 |
| 🟡 **半自动** | 部分匹配迁移规则 / 置信度 70-95% / 涉及多文件联动 | AI 生成 patch → 编译验证 → **人工审核** → 回归测试 | Owner 审核通过 | 审核后合入 |
| 🔴 **人工** | 全新 API / 无匹配规则 / 置信度 < 70% / 涉及架构变更 | 生成适配任务清单 + 参考建议 | Owner 手动适配 | 手动产出 |

### 6.2 置信度评估维度

| 维度 | 权重 | 评估方式 |
|------|------|---------|
| API 迁移规则匹配度 | 40% | 规则库中是否有完全匹配的迁移规则 |
| 代码变更复杂度 | 20% | 涉及文件数、改动行数、是否有连锁影响 |
| 上下文确定性 | 20% | 是否需要运行时判断、是否依赖设备状态 |
| 历史成功率 | 15% | 类似迁移模式的历史成功率 |
| 测试覆盖度 | 5% | 是否有对应的测试用例可验证迁移正确性 |

### 6.3 策略偏好自定义

Owner 可以在 `version-adaptation.yaml` 中通过 `strategy_preferences` 调整阈值：

```yaml
strategy_preferences:
  auto_confidence_threshold: 0.95   # 提高此值 → 更保守，更多走半自动/人工
  semi_auto_min_confidence: 0.70    # 降低此值 → 更多走半自动而非人工
  batch_size: 50                    # 每批处理数量
  parallel_agents: 4                # 并行处理 Agent 数量
```

> **注意**: 不建议将 `auto_confidence_threshold` 降到 0.90 以下。全自动适配缺乏人工审核环节，过低的阈值会引入质量风险。

---

## 7. 验收标准与质量门禁

### 7.1 三级质量门禁

| 级别 | 门禁 | 条件 | 失败处理 |
|------|------|------|---------|
| **P0 - 编译门禁** | 编译通过 | 100% 编译通过，0 error，0 warning | **直接 BLOCK**，不允许继续 |
| **P1 - 回归门禁** | 冒烟+功能回归 | 回归通过率 ≥ 95% | 人工审核后决定是否放行 |
| **P2 - 人工审核** | Owner Review | 半自动适配项需 Owner 确认 | Owner 确认或退回重做 |

### 7.2 门禁执行规则

```
全自动适配项:
  编译 → PASS → 回归 → PASS → ✅ 自动合入
                   → FAIL → ❌ 降级为半自动

半自动适配项:
  编译 → PASS → 回归 → PASS → 人工审核 → ✅ 合入
                   → FAIL → ❌ 退回重做
         → FAIL → ❌ 退回重做

人工适配项:
  产出适配任务清单 + 参考建议 → Owner 手动处理
```

### 7.3 适配报告标准格式

每次适配执行完毕后，系统自动生成适配报告：

```markdown
# 版本适配报告 — {module_name}

## 基本信息
- 模块: {module_name}
- 源版本: {source_version}
- 目标版本: {target_version}
- 执行时间: {timestamp}
- 执行人: TAHP Adaptation Engine

## 适配统计

| 策略 | 计划数 | 完成数 | 通过率 |
|------|--------|--------|--------|
| 全自动 | N | N | N% |
| 半自动 | N | N | N% |
| 人工 | N | N | N% |
| **合计** | **N** | **N** | **N%** |

## 质量门禁

| 门禁 | 结果 | 详情 |
|------|------|------|
| 编译 | PASS/FAIL | error: N, warning: N |
| 冒烟测试 | PASS/FAIL | 通过: N/N |
| 功能回归 | PASS/FAIL | 通过率: N% |
| 人工审核 | 待审核/已审核 | 待审核: N 项 |

## 待处理项
- [ ] {待人工处理的适配项及原因}
- [ ] {待审核的半自动适配项}

## API 迁移规则更新
- 新增规则: N 条
- 更新规则: N 条
- 规则库总规模: N 条
```

---

## 8. 跨版本经验复用机制

### 8.1 复用层次

```
Level 1 — API 迁移规则复用
  A15→A16 积累的迁移规则 → A16→A17 直接使用
  存储: constraints/shared/api-migration-rules/

Level 2 — 适配 Skill 复用
  EvoSkill 进化后的适配 Skill → 下次升级直接加载
  存储: skills/.claude/skills/{module}-version-adapter/

Level 3 — 适配模式复用
  成功的适配策略/流程 → 同步到其他模块
  机制: EvoSkill 跨模块 Frontier 共享
```

### 8.2 规则库版本管理

```
每次版本升级适配完成后:
  1. 将新发现的迁移规则追加到 api-migration-rules/
  2. 更新已有规则的 verified_in 字段
  3. 调整与实际成功率偏差过大的 confidence 值
  4. Git commit: "Add migration rules from A15→A16 adaptation"
  5. 打 Tag: migration-rules/v1.0-a16

下次版本升级时:
  1. 检出最新的规则库
  2. 运行 aosp-diff-analyzer 获取新版本差异
  3. 自动匹配已有规则 → 确定全自动/半自动/人工比例
  4. 未匹配的变更 → 作为新候选规则，适配成功后入库
```

### 8.3 跨模块经验共享

```
通信模块在 A15→A16 中踩过的坑:
  - TelephonyManager API 签名变更 → 规则 TEL-001
  - PhoneFactory 返回类型变更 → 规则 TEL-002

驱动模块在 A15→A16 中踩过的坑:
  - kernel_device_type 结构体变更 → 规则 KRN-001

下次 A16→A17 时:
  - 通信模块的规则 → 直接复用
  - 驱动模块的规则 → 直接复用
  - 两个模块如果有共性变更 → 规则自动交叉匹配
```

---

## 9. 质量检查清单

### 9.1 约束文件质量检查

Owner 提交约束文件后，系统自动执行以下检查：

| # | 检查项 | 级别 | 自动检查方式 |
|---|--------|------|------------|
| 1 | 所有必填字段已填写 | P0 | YAML Schema 验证 |
| 2 | 模块 name 符合 kebab-case | P0 | 正则匹配 |
| 3 | version 遵循 semver 格式 | P0 | 正则匹配 |
| 4 | `adaptation_constraints` 至少 3 条 | P0 | 计数检查 |
| 5 | `acceptance_criteria.compile_pass` 为 true | P0 | 值检查 |
| 6 | `regression_pass_rate` ≥ 0.90 | P1 | 值检查 |
| 7 | `codebase_paths` 中的路径实际存在 | P1 | 文件系统检查 |
| 8 | `api_migration_rules` 中引用的共享规则文件存在 | P1 | 文件系统检查 |
| 9 | `build_targets` 中的目标在 build system 中已定义 | P1 | 构建系统验证 |
| 10 | 内联规则的 confidence 在 [0.0, 1.0] 范围内 | P1 | 范围检查 |
| 11 | `auto_confidence_threshold` ≥ 0.90 | P2 | 值检查 |
| 12 | `smoke_test_targets` 至少 3 项 | P2 | 计数检查 |
| 13 | 约束文件已在 Git 中提交 | P2 | Git 状态检查 |

### 9.2 适配执行质量检查

| # | 检查项 | 级别 | 触发时机 |
|---|--------|------|---------|
| 1 | 所有 patch 通过 checkpatch / lint | P0 | 编译前 |
| 2 | 编译 0 error 0 warning | P0 | 编译后 |
| 3 | 全自动 patch 的变更文件数 ≤ 预期范围 | P1 | 生成后 |
| 4 | 无意外的文件被修改 | P1 | 生成后 |
| 5 | 冒烟测试 100% 通过 | P0 | 回归前 |
| 6 | 功能回归通过率 ≥ 95% | P1 | 回归后 |
| 7 | 半自动 patch 已有 Owner 审核记录 | P2 | 合入前 |
| 8 | 适配报告已生成 | P2 | 完成后 |
| 9 | 新迁移规则已提取并入库 | P2 | 完成后 |

### 9.3 Owner 自检清单

在提交约束文件前，Owner 应确认：

- [ ] `codebase_paths` 是否覆盖了模块的所有代码路径
- [ ] `excluded_paths` 是否正确排除了不需要适配的路径
- [ ] `api_migration_rules` 中内联规则是否经过实际验证
- [ ] `adaptation_constraints` 是否覆盖了模块的关键红线
- [ ] `acceptance_criteria` 中的测试目标是否在当前测试框架中可用
- [ ] `eval_dataset` 中是否准备了上一次适配的典型案例
- [ ] `strategy_preferences` 中的阈值是否符合团队质量要求

---

## 10. 附录

### 10.1 与其他规范的关系

| 本规范章节 | 关联文档 | 关系 |
|-----------|---------|------|
| 约束文件通用原则 | [TAHP-约束文件编写规范](TAHP-约束文件编写规范.md) | 通用原则的适配引擎特化 |
| 代码生成约束 | [TAHP-AI代码生成约束规范](TAHP-AI代码生成约束规范.md) | 适配 patch 生成时遵守 |
| 评估与质量门禁 | [TAHP-评估与质量门禁规范](TAHP-评估与质量门禁规范.md) | 适配 Skill 的评估遵循 |
| 设计文档 | [TECNO-AI-Harness-Platform-方案设计.md](TECNO-AI-Harness-Platform-方案设计.md) 第7章 | 适配引擎详细设计 |

### 10.2 change_type 枚举值定义

| 值 | 说明 | 自动迁移难度 |
|---|------|------------|
| `method_signature` | 方法签名变更（参数/返回值改变） | 中 |
| `method_rename` | 方法重命名 | 低 |
| `constant_moved` | 常量从一类迁移到另一类 | 低 |
| `class_relocated` | 类从一包迁移到另一包 | 中 |
| `interface_changed` | 接口方法增减 | 高 |
| `deprecated_removed` | API 从废弃变为移除 | 低 |
| `behavior_changed` | API 行为语义变更 | 高 |
| `new_replacement` | 新 API 替代旧 API | 中 |

### 10.3 版本历史

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| v1.0 | 2026-05-18 | 初始版本，覆盖 version_adaptation + carrier_porting 两大场景 |
