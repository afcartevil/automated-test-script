---
name: p1-upgrade-skill
description: 大版本升级 P1 阶段的主控技能，集成 MODEM + AP 侧所有子技能。当用户提到 "P1 升级"、"大版本升级"、"P1_UPGRADE" 时触发。只做参数收集和工作流调度，不直接修改任何文件。
tools: Read, Glob, Bash
---

# P1 大版本升级主控技能（集成 MODEM + AP）

## 技能概述
本技能是大版本升级 P1 阶段的主控技能，集成了 MODEM_SKILL 和 AP_SKILL，实现参数的统一管理和传递，减少用户重复输入。

## 技能目录结构
```
P1_UPGRADE_SKILL/
├── SKILL.md                          # 主控技能配置
├── scripts/
│   └── master_execution_workflow.md  # 主控执行工作流
├── MODEM_SKILL/                      # MODEM 侧子技能
│   ├── SKILL.md
│   ├── scripts/master_execution_workflow.md
│   ├── rf_param_skill/               # RF 参数移植
│   ├── macro_control_skill/          # 宏控移植
│   └── lock_nv_skill/                # 锁卡 NV 修改
└── AP_SKILL/                         # AP 侧子技能
    ├── project_file_skill/           # 工程文件修改
    ├── gpio_check_skill/             # GPIO 检查
    └── product_repo_skill/           # 产物仓创建
```

## 子技能路径配置

| 子技能名称 | 相对路径 | 说明 |
|------------|----------|------|
| rf_param_skill | ./MODEM_SKILL/rf_param_skill/ | RF 参数移植 |
| macro_control_skill | ./MODEM_SKILL/macro_control_skill/ | 宏控移植 |
| lock_nv_skill | ./MODEM_SKILL/lock_nv_skill/ | 锁卡 NV 修改 |
| project_file_skill | ./AP_SKILL/project_file_skill/ | 工程文件修改 |
| gpio_check_skill | ./AP_SKILL/gpio_check_skill/ | GPIO 检查 |
| product_repo_skill | ./AP_SKILL/product_repo_skill/ | 产物仓创建

## 输入参数（统一收集）

| 参数名 | 类型 | 描述 | 所属技能 |
|--------|------|------|----------|
| **Path_A_Pub** | string | 代码A（原分支）的公共仓路径 | MODEM |
| **Path_A_Priv** | string | 代码A（原分支）的私有仓路径 | MODEM |
| **Path_B_Pub** | string | 代码B（目标分支）的公共仓路径 | MODEM + AP |
| **Path_B_Priv** | string | 代码B（目标分支）的私有仓路径 | MODEM |
| **BOM_Name** | string | 原 BOM 名称 | MODEM |
| **BOM_Name_Target** | string | 更新后的 BOM 名称 | MODEM + AP |
| **RF_TARGET_LOCATION** | string | RF 参数目标位置（public/private） | MODEM |
| **AP_Project_Path** | string | AP 工程文件代码路径 | AP |
| **GPIO_Path_C** | string | GPIO 检查升级前路径 | AP |
| **GPIO_Path_D** | string | GPIO 检查升级后路径 | AP |
| **Is_TOS16_Before** | boolean | 是否为 TOS16 之前的版本 | AP |

## 执行流程

### 阶段 1：参数收集（一次性收集所有参数）
```
┌─────────────────────────────────────────────────────────────┐
│                    参数收集阶段                              │
├─────────────────────────────────────────────────────────────┤
│  1. 收集 MODEM 侧参数                                       │
│     - Path_A_Pub, Path_A_Priv                              │
│     - Path_B_Pub, Path_B_Priv                              │
│     - BOM_Name, BOM_Name_Target                            │
│     - RF_TARGET_LOCATION                                   │
├─────────────────────────────────────────────────────────────┤
│  2. 收集 AP 侧参数                                          │
│     - AP_Project_Path                                      │
│     - GPIO_Path_C, GPIO_Path_D                             │
│     - Is_TOS16_Before                                      │
└─────────────────────────────────────────────────────────────┘
```

### 阶段 2：MODEM 侧处理
```
┌─────────────────────────────────────────────────────────────┐
│                    MODEM 侧处理                            │
├─────────────────────────────────────────────────────────────┤
│  1. RF 参数移植子技能                                       │
│     - 使用参数：Path_A_Pub, Path_A_Priv, Path_B_Pub,        │
│                Path_B_Priv, BOM_Name, BOM_Name_Target,      │
│                RF_TARGET_LOCATION                           │
├─────────────────────────────────────────────────────────────┤
│  2. 宏控移植子技能                                          │
│     - 使用参数：Path_A_Pub, Path_A_Priv, Path_B_Pub,        │
│                Path_B_Priv, BOM_Name, BOM_Name_Target       │
├─────────────────────────────────────────────────────────────┤
│  3. 锁卡 NV 修改子技能（可选）                               │
│     - 使用参数：Path_B_Pub, BOM_Name_Target                 │
└─────────────────────────────────────────────────────────────┘
```

### 阶段 3：AP 侧处理（可选）
```
┌─────────────────────────────────────────────────────────────┐
│                     AP 侧处理                               │
├─────────────────────────────────────────────────────────────┤
│  1. 工程文件修改子技能                                       │
│     - 使用参数：BOM_Name_Target（继承自 MODEM）              │
│     - 使用参数：AP_Project_Path                             │
├─────────────────────────────────────────────────────────────┤
│  2. GPIO 检查子技能                                          │
│     - 使用参数：BOM_Name_Target（继承自 MODEM）              │
│     - 使用参数：GPIO_Path_C, GPIO_Path_D, Is_TOS16_Before   │
├─────────────────────────────────────────────────────────────┤
│  3. 产物仓创建子技能                                         │
│     - 使用参数：BOM_Name_Target（继承自 MODEM）              │
│     - 使用参数：Path_B_Pub（继承自 MODEM）                   │
└─────────────────────────────────────────────────────────────┘
```

### 阶段 4：结果汇总
```
┌─────────────────────────────────────────────────────────────┐
│                    结果汇总                                  │
├─────────────────────────────────────────────────────────────┤
│  1. MODEM 侧处理结果                                        │
│     - RF 参数移植状态                                       │
│     - 宏控移植状态                                          │
│     - 锁卡 NV 修改状态                                      │
├─────────────────────────────────────────────────────────────┤
│  2. AP 侧处理结果                                           │
│     - 工程文件修改状态                                       │
│     - GPIO 检查状态                                         │
│     - 产物仓创建状态                                        │
└─────────────────────────────────────────────────────────────┘
```

## 参数传递关系

### 从 MODEM 传递到 AP 的参数

| 参数名 | 传递方式 | 用途 |
|--------|----------|------|
| **BOM_Name_Target** | 直接传递 | 工程文件修改、GPIO 检查、产物仓创建 |
| **Path_B_Pub** | 直接传递 | 产物仓创建（查找产物仓文件夹） |

### 参数继承流程图

```
用户输入参数
    ↓
┌───────────────────────┐
│   P1_UPGRADE_SKILL    │  ← 主控技能（统一管理）
└───────────┬───────────┘
            │
     ┌──────┴──────┐
     ↓             ↓
┌──────────┐ ┌──────────┐
│MODEM_SKILL│ │ AP_SKILL │
└──────────┘ └──────────┘
     │             │
     ↓             ↓
  RF参数移植    工程文件修改
  宏控移植      GPIO检查
  锁卡NV修改    产物仓创建
```

## 输出结果

| 输出项 | 类型 | 描述 |
|--------|------|------|
| success | boolean | 整体操作是否成功 |
| message | string | 执行结果描述 |
| modem_result | object | MODEM 侧处理结果 |
| ap_result | object | AP 侧处理结果 |

## 调用方式

```json
{
  "skill_name": "P1_UPGRADE_SKILL",
  "action": "execute",
  "parameters": {
    "Path_A_Pub": "Z:\\test-99U\\TK_MD_MOLY.NR17.R1.MP3.RC.MP_U0",
    "Path_A_Priv": "Z:\\test-99U\\Tran_modem_U",
    "Path_B_Pub": "Z:\\modem\\S\\99U\\TK_MD_MOLY.NR17.R1.MP3.RC.MP_U0",
    "Path_B_Priv": "Z:\\modem\\S\\99U\\Tran_modem_U",
    "BOM_Name": "cm8_h973_a1",
    "BOM_Name_Target": "cm8_h973_a1_W",
    "RF_TARGET_LOCATION": "public",
    "AP_Project_Path": "Z:\\U-AP\\vendor\\transsion\\projects",
    "GPIO_Path_C": "Z:\\S-AP\\tran_projects\\km9\\km9_h357_e1\\km9\\vendor\\mediatek\\proprietary\\tools\\dct\\dws\\mt6835",
    "GPIO_Path_D": "Z:\\U-AP\\vendor\\mediatek\\proprietary\\tools\\dct\\dws\\mt6878",
    "Is_TOS16_Before": true
  }
}
```

## 上下文变量管理

### 全局上下文变量

| 变量名 | 生命周期 | 说明 |
|--------|----------|------|
| global_context | 整个升级流程 | 存储所有用户输入参数 |
| modem_context | MODEM 侧处理 | MODEM 子技能产生的中间变量 |
| ap_context | AP 侧处理 | AP 子技能产生的中间变量 |

### 参数传递机制

1. **一次性收集**：所有参数在技能开始时一次性收集完成
2. **全局存储**：参数存储在全局上下文中，所有子技能均可访问
3. **自动继承**：AP 子技能自动继承 MODEM 侧已收集的参数
4. **状态传递**：MODEM 侧处理完成后，状态传递给 AP 侧

## 异常处理

### 参数缺失处理
- 如果缺少 MODEM 侧必需参数：终止执行并提示用户
- 如果缺少 AP 侧必需参数：跳过 AP 侧处理

### 子技能失败处理
- MODEM 侧子技能失败：提示用户，询问是否继续 AP 侧处理
- AP 侧子技能失败：记录错误，继续执行其他子技能

### 回滚机制
- RF 参数移植失败：提示用户手动处理
- 宏控移植失败：保留修改记录，提示用户检查
- AP 侧处理失败：保留已完成的修改，提示用户检查

## 安全机制

### 参数验证
- 路径有效性检查
- 参数格式验证
- 必填参数检查

### 操作确认
- 危险操作前提示用户确认
- 重要修改前自动备份

### 日志记录
- 详细记录每一步操作
- 记录参数值（敏感信息脱敏）
- 记录操作时间和结果