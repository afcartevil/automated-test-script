# 宏控子技能参考数据格式

## 输入数据格式

### 参数结构
```json
{
  "common_path": "/workspace/project/common/",
  "X": "RF_V2.1.0",
  "Y": "CONFIG_TYPE_A",
  "bom_name": "MDM9607_LA_10.0.0"
}
```

### 参数说明
| 参数名 | 类型 | 说明 |
|--------|------|------|
| common_path | string | 公共仓路径 |
| X | string | RF参数版本号 |
| Y | string | RF参数配置标识 |
| bom_name | string | BOM名称 |

## 输出数据格式

### 结果结构
```json
{
  "success": true,
  "message": "宏控代码修改完成",
  "modified_files": 3,
  "modified_locations": 6,
  "details": [
    {
      "file": "platform/common/macros.h",
      "changes": [
        {
          "type": "add",
          "line": 45,
          "content": "#define RF_VERSION \"RF_V2.1.0\""
        },
        {
          "type": "modify",
          "line": 52,
          "old_content": "#define CONFIG_TYPE CONFIG_TYPE_B",
          "new_content": "#define CONFIG_TYPE CONFIG_TYPE_A"
        }
      ]
    },
    {
      "file": "platform/common/version.h",
      "changes": [
        {
          "type": "add",
          "line": 120,
          "content": "#ifdef NEW_RF_VERSION\n#define FEATURE_RF_ENABLED 1\n#endif"
        }
      ]
    }
  ],
  "timestamp": "2024-01-15T10:30:00Z"
}
```

### 输出字段说明
| 字段名 | 类型 | 说明 |
|--------|------|------|
| success | boolean | 执行是否成功 |
| message | string | 结果描述信息 |
| modified_files | integer | 修改的文件数量 |
| modified_locations | integer | 修改的代码位置数量 |
| details | array | 修改详情列表 |
| details[].file | string | 修改的文件名 |
| details[].changes | array | 该文件的修改列表 |
| details[].changes[].type | string | 修改类型（add/modify/delete） |
| details[].changes[].line | integer | 修改位置的行号 |
| details[].changes[].content | string | 添加或修改后的内容 |
| details[].changes[].old_content | string | 修改前的内容（仅modify类型） |
| timestamp | string | 执行时间戳 |

## 错误输出格式

### 错误结构
```json
{
  "success": false,
  "message": "路径验证失败：公共仓路径不存在",
  "error_code": "PATH_NOT_FOUND",
  "details": {
    "path": "/invalid/path/",
    "suggestion": "请检查路径是否正确"
  }
}
```

### 错误码说明
| 错误码 | 说明 |
|--------|------|
| PATH_NOT_FOUND | 路径不存在 |
| PERMISSION_DENIED | 权限不足 |
| NO_MACRO_FILES | 未找到宏控文件 |
| MODIFICATION_FAILED | 修改失败 |
| UNKNOWN_ERROR | 未知错误 |
