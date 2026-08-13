# Makefile (.mk) 修改规范

## 概述
本参考文档定义了 AI 在修改 `ProjectConfig.mk` 文件时应遵循的规范和最佳实践。

## 匹配灵活性

### 支持的赋值语句格式
AI 需要支持以下多种赋值格式：

| 格式示例 | 说明 |
|----------|------|
| `CUSTOM_MODEM=xxx` | 无空格格式 |
| `CUSTOM_MODEM = xxx` | 标准空格格式 |
| `CUSTOM_MODEM =xxx` | 左侧有空格 |
| `CUSTOM_MODEM= xxx` | 右侧有空格 |
| `CUSTOM_MODEM = xxx  ` | 末尾有空格 |
| `CUSTOM_MODEM = xxx # comment` | 带有注释 |

### 正则表达式推荐
使用以下正则表达式模式进行匹配：

```regex
CUSTOM_MODEM\s*=\s*([^\s#]*)
```

**解释：**
- `CUSTOM_MODEM`：精确匹配宏名
- `\s*`：匹配零个或多个空白字符（包括空格、制表符）
- `=`：匹配等号
- `\s*`：匹配等号后的零个或多个空白字符
- `([^\s#]*)`：捕获等号后到空格或注释符之前的内容

## 精准替换规则

### 替换范围
仅替换等号（`=`）到行尾或注释符（`#`）之前的内容。

### 替换示例

**原始内容：**
```makefile
CUSTOM_MODEM = old_bom_name  # original setting
```

**替换后：**
```makefile
CUSTOM_MODEM = new_bom_name  # original setting
```

**注意事项：**
- ✅ 保留原始注释
- ✅ 保留原始缩进
- ✅ 保留等号两侧的空格
- ❌ 不修改注释内容
- ❌ 不删除行尾空格

### 替换逻辑流程

```
输入行: CUSTOM_MODEM = old_value  # some comment
            ↓
    提取宏名部分: CUSTOM_MODEM =
            ↓
    提取注释部分:  # some comment
            ↓
    拼接新值: CUSTOM_MODEM = new_value
            ↓
    添加注释: CUSTOM_MODEM = new_value  # some comment
            ↓
    输出结果
```

## 文件格式保护

### 缩进保持
- 保持原文件的缩进风格（空格或制表符）
- 不改变行首空格数量

### 编码处理
- 保持原文件的字符编码（UTF-8 或 GBK）
- 不添加 BOM 标记

### 行尾处理
- 保持原文件的换行符风格（LF 或 CRLF）
- 不在文件末尾添加额外空行

## 错误处理

### 宏未找到
如果 `CUSTOM_MODEM` 宏未找到，应：
1. 在文件末尾添加新的宏定义
2. 使用标准格式：`CUSTOM_MODEM = $(BOM_Name_Target)`

### 文件不存在
如果 `ProjectConfig.mk` 文件不存在，应：
1. 返回错误信息
2. 提示用户确认路径是否正确

### 权限不足
如果没有写入权限，应：
1. 返回错误信息
2. 提示用户检查文件权限

## 安全机制

### 自动备份
修改前自动创建备份文件：
- 备份文件名：`ProjectConfig.mk.backup`
- 备份位置：同目录下

### 事务性修改
确保修改失败时可以恢复到原始状态。

## 验证方法

### 修改后验证
修改完成后应验证：
1. 文件是否正确保存
2. 宏值是否正确更新
3. 文件格式是否保持一致

### 验证命令示例
```bash
# 检查宏值
grep "CUSTOM_MODEM" ProjectConfig.mk

# 检查文件格式
cat -A ProjectConfig.mk | head -n 5
```

## 示例代码

### PowerShell 实现示例

```powershell
Function UpdateCustomModem {
    param(
        [string]$filePath,
        [string]$newBomName
    )
    
    # 读取文件内容
    $content = Get-Content -Path $filePath -Raw
    
    # 定义正则表达式模式
    $pattern = '(CUSTOM_MODEM\s*=\s*)[^\s#]*(\s*#.*)?'
    
    # 检查是否存在宏定义
    if ($content -match $pattern) {
        # 提取前缀（宏名 + 等号 + 空格）
        $prefix = $matches[1]
        # 提取注释（如果有）
        $comment = $matches[2]
        
        # 构建新的宏定义行
        $newLine = $prefix + $newBomName + $comment
        
        # 执行替换
        $newContent = $content -replace $pattern, $newLine
        
        # 保存修改
        Set-Content -Path $filePath -Value $newContent -NoNewline
        
        return @{ success = $true; message = "修改成功" }
    } else {
        # 如果宏不存在，在文件末尾添加
        $newLine = "`nCUSTOM_MODEM = $newBomName"
        $newContent = $content.TrimEnd() + $newLine
        Set-Content -Path $filePath -Value $newContent -NoNewline
        
        return @{ success = $true; message = "宏不存在，已添加" }
    }
}
```

## 参考资料

- [GNU Make 官方文档](https://www.gnu.org/software/make/manual/)
- [Makefile 最佳实践](https://makefiletutorial.com/)