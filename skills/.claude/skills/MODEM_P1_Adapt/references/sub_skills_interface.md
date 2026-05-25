# MODEM升级子技能接口说明

## 概述
本文档定义了MODEM大版本升级主控技能与子技能之间的接口规范。

## 接口架构

### 主控技能 → RF参数移植子技能

#### 请求
```json
{
  "skill_name": "rf_param_skill",
  "action": "execute",
  "parameters": {
    "Path_A_Priv": "代码A（原分支）的私有仓路径",
    "Path_A_Pub": "代码A（原分支）的公共仓路径",
    "Path_B_Priv": "代码B（目标分支）的私有仓路径",
    "Path_B_Pub": "代码B（目标分支）的公共仓路径",
    "BOM_Name": "项目BOM名称（ae10_h833_a1, cm7_h781, x6870_h781_f1, lk7k_h582）",
    "BOM_Name_Target": "变更后的BOM名称（x6856_h971_a1）",
    "RF_TARGET_LOCATION": "RF参数目标位置（public/private）"
  }
}
```

#### 响应
```json
{
  "skill_name": "rf_param_skill",
  "status": "success",
  "result": {
    "message": "RF参数移植成功，从私有仓移植到公共仓，共复制5个文件",
    "source_location": "Priv",
    "target_location": "Pub",
    "file_count": 5,
    "variables": {
      "X": "RF_V2.1.0",
      "Y": "CONFIG_TYPE_A"
    }
  }
}
```

### 主控技能 → 公共仓宏控子技能

#### 请求
```json
{
  "skill_name": "macro_control_skill",
  "action": "execute",
  "parameters": {
    "Path_A_Pub": "代码A（原分支）的公共仓路径",
    "Path_B_Pub": "代码B（目标分支）的公共仓路径",
    "X": "RF_V2.1.0",
    "Y": "CONFIG_TYPE_A"
  }
}
```

#### 响应
```json
{
  "skill_name": "macro_control_skill",
  "status": "success",
  "result": {
    "message": "宏控代码修改完成，共修改3个文件，6处代码",
    "modified_files": 3,
    "modified_locations": 6,
    "details": [...]
  }
}
```

## 参数传递规范

### 全局输入参数（由主控技能收集并保存）
| 变量名 | 类型 | 说明 |
|--------|------|------|
| Path_A_Pub | string | 代码A（原分支）的公共仓路径 |
| Path_A_Priv | string | 代码A（原分支）的私有仓路径 |
| Path_B_Pub | string | 代码B（目标分支）的公共仓路径 |
| Path_B_Priv | string | 代码B（目标分支）的私有仓路径 |
| BOM_Name | string | 项目BOM名称 |
| BOM_Name_Target | string | 变更后的BOM名称 |
| RF_TARGET_LOCATION | string | RF参数目标位置（public/private） |

### 上下文变量
| 变量名 | 类型 | 来源 | 传递方向 |
|--------|------|------|----------|
| X | string | RF参数移植子技能 | RF子技能 → 主控技能 → 宏控子技能 |
| Y | string | RF参数移植子技能 | RF子技能 → 主控技能 → 宏控子技能 |

### 状态码
| 状态码 | 说明 |
|--------|------|
| success | 执行成功 |
| failed | 执行失败 |
| pending | 等待用户输入 |

## 错误处理机制

### 错误响应格式
```json
{
  "skill_name": "rf_param_skill",
  "status": "failed",
  "error": {
    "code": "PATH_NOT_FOUND",
    "message": "路径不存在",
    "suggestion": "请检查路径是否正确"
  }
}
```

### 错误码说明
| 错误码 | 说明 |
|--------|------|
| PATH_NOT_FOUND | 路径不存在 |
| BOM_NOT_FOUND | 未找到BOM名称对应的项目文件夹 |
| PERMISSION_DENIED | 权限不足 |
| NO_MACRO_FILES | 未找到宏控文件 |
| MODIFICATION_FAILED | 修改失败 |
| UNKNOWN_ERROR | 未知错误 |

## 执行流程时序

```
用户输入 → 主控技能（收集4个路径 + BOM名称 + RF目标位置）→ RF参数移植子技能（智能发现RF位置）→ 主控技能（获取X,Y）→ 公共仓宏控子技能 → 主控技能 → 用户
     ↓                        ↓                                         ↓                        ↓
   输入参数              执行RF移植（Priv→Pub）                    获取变量X,Y              执行宏控修改          输出结果
```

## 版本兼容性

### 接口版本
- 当前版本: v1.0
- 向后兼容: 支持v1.0及以上版本

### 版本升级策略
- 子技能版本独立升级
- 主控技能需要兼容多个子技能版本
- 升级时保持向后兼容
