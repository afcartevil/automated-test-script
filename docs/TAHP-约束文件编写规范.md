# TAHP 约束文件编写规范

> **版本**: v3.0 | **日期**: 2026-05-20 | **适用范围**: 所有业务模块Owner
> **状态**: Approved
> **v3.0 变更**: 对齐方案设计v3.0 — 新增v3.0脚本引用表、knowledge-to-skill-pipeline.yaml Playbook引用、版本历史
> **v2.0 变更**: 适配知识库体系 — 约束文件可由系统从知识库自动提取生成，Owner 可选审核微调

---

## 1. 目的与原则

### 1.1 核心目的

约束文件是业务Owner与TAHP系统之间的**唯一接口**。Owner不需要编写SOP、不需要理解AI内部机制，只需要用结构化的方式描述：
- **模块边界**：这个模块管什么、不管什么
- **代码规则**：不能违反什么架构约定
- **质量标准**：怎样才算做好了
- **历史知识**：过去的Bug/问题长什么样

> **v3.0 变更**: 约束文件不再需要 Owner 从零手写。系统可从知识库自动提取生成约束文件，Owner 仅需审核确认或微调。手动编写仍作为高级选项保留。详见[方案设计 §8 知识库系统设计](TECNO-AI-Harness-Platform-方案设计.md#8-知识库系统设计)。

### 1.2 编写原则

| # | 原则 | 说明 |
|---|------|------|
| 1 | **声明式，非指令式** | 描述"是什么"和"不能做什么"，不要描述"怎么做"。系统会根据约束自动生成执行步骤 |
| 2 | **可验证** | 每条规则必须可以通过自动化手段检验（编译检查、日志pattern匹配、测试用例等） |
| 3 | **具体，不模糊** | "代码要规范"→"必须通过checkpatch.pl检查，零warning"。禁止无量化标准的描述 |
| 4 | **最小必要** | 只写当前模块特有的约束，通用规则放在 `shared/` 目录，避免重复 |
| 5 | **版本化** | 每次修改约束文件必须通过Git提交，附带修改说明 |
| 6 | **知识驱动** | 约束文件可由系统从知识库自动提取生成(v3.0)；手动编写时也应参考知识库中已有的经验案例和错误模式 |

---

## 2. 文件格式规范

### 2.1 目录结构

```
constraints/
├── {module-name}/
│   ├── module.yaml              # 模块基本信息（必须）
│   ├── bug-analysis.yaml        # Bug分析约束（推荐）
│   ├── code-adaptation.yaml     # 代码适配约束（推荐）
│   └── eval-data/               # 评估数据集（必须）
│       ├── cases/               # 测试案例（YAML格式）
│       └── expected/            # 期望输出（JSON格式）
└── shared/
    ├── coding-standards.yaml    # 全局编码规范
    └── android-platform.yaml    # Android平台通用约束
```

### 2.1.1 知识库自动生成约束 (v3.0)

v3.0 引入知识库后，约束文件可以由系统自动生成：

```
知识库 (knowledge-base/{module}/)
  ├── docs/          技术文档
  ├── cases/         经验案例
  └── auto/          自动沉淀
        │
        ↓ feed_knowledge.py → 知识到约束 Pipeline
        ↓
约束文件 (constraints/{module}/)
  ├── module.yaml            自动提取
  ├── bug-analysis.yaml      自动提取
  ├── code-adaptation.yaml   自动提取
  └── eval-data/             从案例自动生成
```

使用方法：
```bash
# 投喂文档后自动生成约束
python scripts/feed_knowledge.py --module {module} --docs ./docs/*.md

# 手动触发约束重新提取
python scripts/extract_constraints.py --module {module}
```

### 2.2 命名规则

| 类型 | 命名格式 | 示例 |
|------|---------|------|
| 模块目录 | `{kebab-case}` | `telephony/`, `kernel-driver/`, `power-mgmt/` |
| 约束文件 | `{domain}.yaml` | `bug-analysis.yaml`, `code-adaptation.yaml` |
| 测试案例 | `{case-id}.yaml` | `case-001-volte-drop.yaml` |
| 期望输出 | `{case-id}.json` | `case-001-volte-drop.json` |

---

## 3. 模块基本信息 (module.yaml)

**必须文件**。定义模块的身份和归属。

```yaml
# ===== 模块元信息（必须填写） =====
module:
  name: telephony                    # 模块唯一标识符（kebab-case）
  display_name: "通信模块"            # 中文显示名
  domain: android-telephony          # 技术域
  owner: zhangsan                    # 负责人（工号或邮箱）
  team: comm-integration             # 所属团队
  version: "1.0"                     # 约束文件版本号
  created: "2026-05-18"
  updated: "2026-05-18"

# ===== 模块边界（必须填写） =====
scope:
  # 包含的子系统/组件
  includes:
    - component: "Telephony Framework"
      path: "frameworks/opt/telephony/"
      description: "Java层电话框架"
    - component: "RILJ (Radio Interface Layer Java)"
      path: "frameworks/base/telephony/"
      description: "RIL Java接口层"
    - component: "RILC (Radio Interface Layer C)"
      path: "hardware/interfaces/ril/"
      description: "RIL C/HIDL层"
    - component: "Modem Interface"
      path: "vendor/mediatek/proprietary/"
      description: "Modem侧接口（只读分析）"

  # 明确排除的区域
  excludes:
    - "frameworks/base/core/java/android/app/"    # 应用框架，非通信
    - "system/core/init/"                          # init系统，非通信
    - "vendor/google/tools/"                       # Google工具，非通信

  # 与其他模块的依赖关系
  dependencies:
    - module: kernel-driver
      type: "runtime"        # runtime / compile-time / analysis-only
      description: "RILC依赖内核驱动提供字符设备节点"
    - module: power-mgmt
      type: "analysis"       # Bug分析时需考虑功耗影响
      description: "通话功耗与基带电源管理相关"
```

### 3.1 必填字段检查清单

- [ ] `module.name` — 唯一标识符
- [ ] `module.owner` — 负责人
- [ ] `scope.includes` — 至少列出1个代码路径
- [ ] `scope.excludes` — 至少列出1个排除区域
- [ ] `scope.dependencies` — 列出跨模块依赖

---

## 4. Bug分析约束 (bug-analysis.yaml)

**推荐文件**。定义AI分析Bug时必须遵守的规则。

```yaml
# ===== Bug分析前置条件（AI必须先确认） =====
preconditions:
  required_info:
    - name: "modem_firmware_version"
      description: "Modem固件版本"
      how_to_get: "getprop gsm.version.baseband"
      required: true                    # 缺少此项则停止分析
      error_msg: "无法在未确认Modem固件版本的情况下进行RIL层分析，请先提供固件版本信息。"

    - name: "android_version"
      description: "Android版本"
      how_to_get: "getprop ro.build.version.release"
      required: true

    - name: "device_model"
      description: "设备型号"
      how_to_get: "getprop ro.product.model"
      required: false                   # 可选信息

    - name: "repro_steps"
      description: "复现步骤"
      how_to_get: "由用户/Bug报告提供"
      required: true
      error_msg: "未提供复现步骤，无法判断是必现还是偶发问题，请补充复现步骤后再分析。"

    - name: "logcat"
      description: "完整logcat日志"
      how_to_get: "adb logcat -d -b radio,main,system"
      required: true
      error_msg: "缺少日志数据，Bug分析需要logcat日志作为输入，请提供完整日志。"

# ===== 分析流程约束 =====
analysis_rules:
  # 层级判定顺序（必须按此顺序执行）
  layer_detection_order:
    1:
      layer: "Framework (Java)"
      check: "搜索logcat中 TelephonyFramework, PhoneInterfaceManager 相关异常"
      indicators:
        - pattern: ".*TelephonyFramework.*Exception"
        - pattern: ".*PhoneInterfaceManager.*Error"
        - pattern: ".*CallManager.*FAIL"

    2:
      layer: "RILJ (Java RIL)"
      check: "搜索RILJ层日志中的错误码和异常"
      indicators:
        - pattern: ".*RILJ.*error"
        - pattern: ".*RIL.*RILConstants"
        - pattern: ".*GsmCdmaPhone.*"

    3:
      layer: "RILC (C/HIDL)"
      check: "搜索RILC层日志，需结合AT命令日志"
      indicators:
        - pattern: ".*RILC.*"
        - pattern: ".*RILD.*"

    4:
      layer: "Modem"
      check: "Modem侧日志分析（如果有AT命令日志）"
      indicators:
        - pattern: ".*ATCMD.*"
        - pattern: ".*MODEM.*"

  # 禁止行为
  prohibited:
    - "在未确认Modem固件版本的情况下给出RIL层Bug结论"
    - "在未确认复现步骤的情况下给出修复代码"
    - "在只有一个案例的情况下推断为通用问题"
    - "修改排除范围内的代码"
    - "忽略安全相关标记（Critical级别的Bug必须单独标注）"

  # 必须产出的分析维度
  required_outputs:
    - name: "root_cause_layer"
      type: "enum"
      values: ["Framework", "RILJ", "RILC", "Modem", "Network", "Unknown"]
      description: "根因所属层级"

    - name: "reproducibility"
      type: "enum"
      values: ["always", "frequent", "occasional", "rare", "unknown"]
      description: "复现概率"

    - name: "impact_scope"
      type: "enum"
      values: ["single_device", "device_series", "platform", "all"]
      description: "影响范围"

    - name: "fix_type"
      type: "enum"
      values: ["code_change", "config_change", "firmware_upgrade", "network_side", "further_investigation"]
      description: "修复类型"

    - name: "severity"
      type: "enum"
      values: ["critical", "high", "medium", "low"]
      description: "严重程度"

    - name: "root_cause_description"
      type: "text"
      min_length: 50
      description: "根因详细描述（不少于50字）"

    - name: "fix_suggestion"
      type: "text"
      min_length: 30
      description: "修复建议（不少于30字）"

# ===== 安全红线 =====
security_gates:
  - condition: "通话可能被窃听"
    action: "标记为critical，立即通知安全团队，不给出公开修复方案"
  - condition: "涉及SIM卡密钥或鉴权数据"
    action: "标记为critical，分析结果仅发送给指定接收人"
  - condition: "可能导致网络拥塞或DoS"
    action: "标记为high，评估影响范围后再修复"
```

### 4.1 评估数据集规范

每个模块必须提供至少 **5个** 历史Bug案例作为评估数据集：

```yaml
# eval-data/cases/case-001-volte-drop.yaml
case:
  id: "case-001"
  title: "VoLTE通话30秒后掉话"
  module: telephony
  severity: "high"
  reproducibility: "always"

input:
  modem_firmware_version: "MP0.H.2-00412"
  android_version: "14"
  device_model: "TECNO-KG5k"
  repro_steps: |
    1. 插入SIM卡A，注册VoLTE
    2. 拨打号码B
    3. 接通后等待约30秒
    4. 通话自动断开
  logcat: "eval-data/cases/case-001-logcat.txt"

expected:
  root_cause_layer: "RILC"
  reproducibility: "always"
  impact_scope: "device_series"
  fix_type: "code_change"
  severity: "high"
  root_cause_description_keywords:
    - "IMS注册"
    - "EPS Fallback"
    - "RILC定时器"
  fix_direction: "RILC层IMS注册状态机超时处理"
```

---

## 5. 代码适配约束 (code-adaptation.yaml)

**推荐文件**。定义AI进行代码适配时的规则。

```yaml
# ===== 编译与构建约束 =====
build_rules:
  build_system: "Android Soong/Make"
  build_command: "source build/envsetup.sh && lunch {target} && m {module}"
  pre_build_checks:
    - command: "checkpatch.pl --no-tree {patch_file}"
      must_pass: true
      error_msg: "补丁未通过checkpatch检查，请修复编码风格问题后重新提交。"

    - command: "scripts/checkpatch.pl --subject {commit_msg}"
      must_pass: true

  post_build_checks:
    - command: "make dtbs_compile -j$(nproc)"
      must_pass: true
      description: "设备树编译验证"

    - command: "grep -r 'Werror' out/target/product/*/obj/"
      must_find_nothing: true
      description: "不允许新增编译警告"

# ===== 代码修改约束 =====
modification_rules:
  # 只能修改的目录
  allowed_paths:
    - "frameworks/opt/telephony/"
    - "frameworks/base/telephony/"
    - "hardware/interfaces/ril/"

  # 绝对不能修改的目录
  forbidden_paths:
    - "frameworks/base/core/"         # 核心框架，影响全局
    - "system/core/"                  # 系统核心
    - "bionic/"                       # C库
    - "external/"                     # 外部库（除非明确授权）

  # 代码风格规则
  style_rules:
    java:
      - "遵循Google Java Style Guide"
      - "使用4空格缩进"
      - "类名使用UpperCamelCase"
      - "方法名使用lowerCamelCase"
      - "常量使用UPPER_SNAKE_CASE"

    cpp:
      - "遵循LLVM Coding Standards"
      - "必须通过clang-format检查"
      - "使用CamelCase命名"

    kernel:
      - "遵循Documentation/process/coding-style.rst"
      - "必须通过checkpatch.pl（零warning）"
      - "缩进使用Tab"

  # 接口变更规则
  interface_change_rules:
    hidl_aidl: "涉及HIDL/AIDL接口变更时，必须同时更新接口定义文件(.hal/.aidl)和所有实现端"
    api_level: "不修改public API签名，如需变更必须经模块Owner审核"
    versioning: "接口变更必须递增版本号"

# ===== 质量红线（零容忍） =====
quality_gates:
  critical:
    - "不允许引入新的编译错误"
    - "不允许修改与目标芯片平台无关的公共代码"
    - "不允许硬编码设备型号或IMEI"
    - "不允许移除已有的错误处理逻辑"
    - "不允许修改安全相关的权限检查代码"

  warning:
    - "不允许新增unused import"
    - "不允许新增TODO/FIXME而不关联Bug ID"
    - "不允许使用已废弃的API（查看@Deprecated注解）"
```

---

## 6. 共享约束 (shared/)

### 6.1 全局编码规范 (coding-standards.yaml)

```yaml
standards:
  version_control:
    commit_message_format: "[{module}] {type}: {description}"
    type_values: ["fix", "feat", "refactor", "test", "docs", "chore"]
    branch_naming: "{type}/{module}/{ticket-id}"

  code_review:
    required_reviewers: 1
    auto_review_checks:
      - "编译通过"
      - "单元测试通过"
      - "checkpatch.pl零warning"
      - "无新增lint错误"

  documentation:
    - "新增公开方法必须有Javadoc/Doxygen注释"
    - "复杂算法必须有内联注释说明思路"
    - "Bug修复的commit message必须关联Bug ID"
```

---

## 7. 质量检查标准

### 7.1 约束文件质量评分

| 维度 | 权重 | 检查项 |
|------|------|--------|
| **完整性** | 30% | 所有必填字段已填写；scope覆盖主要组件；excludes明确 |
| **可验证性** | 25% | 每条规则有明确的检验方法；禁止行为可被自动化检测 |
| **具体性** | 20% | 无模糊描述；有量化标准；有明确的pattern/路径 |
| **最小性** | 15% | 无重复规则；共享规则放在shared/；无冗余信息 |
| **评估集质量** | 10% | 至少5个测试案例；每个案例有完整输入和期望输出 |

### 7.2 审核流程

```
v3.0 约束文件产生方式:
  方式A(推荐): Owner投喂文档 → [知识库解析] → [AI自动提取约束] → [Owner审核] → Git提交 → 系统生效
  方式B(传统): Owner编写 → 自动格式检查 → AI辅助审核 → Owner确认 → Git提交 → 系统生效
               (lint约束文件) (检查字段完整性)  (最终确认)
```

---

## 8. 模板文件

系统提供标准模板，Owner只需复制并填写：

```bash
# 初始化新模块
$ cp -r templates/module-template/ constraints/my-module/
$ cd constraints/my-module/
# 编辑以下文件:
#   module.yaml          ← 模块基本信息（~30分钟）
#   bug-analysis.yaml    ← Bug分析约束（~1小时）
#   code-adaptation.yaml ← 代码适配约束（~1小时）
#   eval-data/           ← 准备5-10个案例（~1小时）
# 总计: ~3.5小时
```

> **v3.0 提示**: 如果已有技术文档和历史案例，推荐使用文档投喂方式：
> ```bash
> python scripts/feed_knowledge.py --module my-module --docs ./my-docs/ --cases ./my-cases/
> ```
> 系统会自动解析文档、提取约束、生成初始 Skill，Owner 只需审核确认。

---

## 9. 与知识库的关系 (v3.0)

### 9.1 知识库驱动约束生成

v3.0 知识库引入后，约束文件的生命周期变为：

```
知识入库 → 自动提取约束 → Owner审核 → 约束生效 → Skill生成/进化
    ↑                                              ↓
    └──────── 执行结果自动沉淀 ←───────────────────┘
```

### 9.2 约束文件的双重来源

| 来源 | 流程 | 适用场景 |
|------|------|---------|
| 知识库自动提取 | feed_knowledge.py → AI提取 → Owner审核 | 新模块接入、知识丰富时 |
| Owner手动编写 | 编辑YAML → validate_constraints.py | 知识不足、需要精确控制时 |

两种来源产出的约束文件格式完全相同，可随时互相替代。

### 9.3 约束文件的质量保障

- 自动提取的约束经过 `validate_constraints.py` 验证完整性
- Owner 审核是必选项（config.yaml 中 `owner_review_required: true`）
- 约束文件的置信度记录在知识库元数据中（`confidence` 字段）
- 低于阈值（默认 0.75）的约束自动标记为 `draft` 状态

---

## 10. v3.0 脚本与 Playbook 引用

以下脚本在 v3.0 知识库系统中可用，与约束文件生命周期直接相关：

| 脚本 | 用途 | 触发方式 |
|------|------|---------|
| `feed_knowledge.py` | 投喂文档/案例到知识库 | Owner 手动触发或 Playbook 自动调用 |
| `extract_constraints.py` | 从知识库自动提取约束文件 | `feed_knowledge.py` 自动链式调用 |
| `query_knowledge.py` | 检索知识库中的相关经验 | Agent 执行前自动调用 |
| `capture_experience.py` | 执行完成后自动沉淀经验 | 任务完成时系统自动调用 |
| `knowledge_stats.py` | 知识库健康度统计与评估 | 定期检查或 Owner 手动触发 |

配套 Playbook：`playbooks/knowledge-to-skill-pipeline.yaml` — 完整的"文档投喂→知识入库→约束提取→Skill生成→EvoSkill进化→执行→经验沉淀"闭环流程。详见[方案设计 §8 知识库系统设计](TECNO-AI-Harness-Platform-方案设计.md#8-知识库系统设计)。

---

## 11. 版本历史

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| v3.0 | 2026-05-20 | 对齐方案设计v3.0 — 新增v3.0脚本引用表、knowledge-to-skill-pipeline.yaml Playbook引用、版本历史 |
| v2.0 | 2026-05-19 | 适配知识库体系 — 约束文件可由系统从知识库自动提取生成，Owner 可选审核微调 |
| v1.0 | 2026-05-18 | 初始版本 |

---

> **关键提醒**: 约束文件的质量直接决定AI生成Skill的质量。花更多时间在约束的精确性和可验证性上，远比花时间写详细SOP有效。记住OpenAI的经验：**"If it cannot be enforced mechanically, agents will deviate."**
