# 产物仓创建规范

## 概述
本参考文档定义了 MODEM 产物仓创建的规范和最佳实践。

## 产物仓结构

### 产物仓路径格式
```
{MODEM公共仓路径}/
├── {BOM_Name_Target}-out_vnd/           # 产物仓文件夹（根据实际文件夹名字匹配）
│   ├── mddata/                          # 调制解调器数据目录（可能存在）
│   ├── modified_files/                  # 修改的文件目录（可能存在）
│   ├── Android.mk                       # Android Makefile（可能存在）
│   ├── *.img                            # MODEM 镜像文件（可能存在）
│   ├── *.bin                            # 二进制文件（可能存在）
│   ├── MDDB.*                           # MODEM 数据库文件（可能存在）
│   └── ...                              # 其他文件（根据实际编译产物而定）
```

### 产物仓识别规则
| 规则 | 说明 |
|------|------|
| 文件夹命名 | `{BOM_Name_Target}-out_vnd`，其中 `{BOM_Name_Target}` 是更新后的 BOM 仓名字 |
| 搜索位置 | 直接在 MODEM 公共仓根目录下查找，不进入二级目录 |
| 匹配方式 | 使用通配符匹配：`*${BOM_Name_Target}-out_vnd*` |
| 内容处理 | **不预设文件结构**，完整复制整个文件夹内容 |

### 产物仓内容说明
产物仓的具体内容会因平台、编译配置、项目需求等因素而异，主要可能包含：
- **镜像文件**：`md1bin.img`、`md1dsp.img`、`single_bin_modem.bin` 等
- **数据库文件**：`MDDB.*` 系列文件
- **调试文件**：`*.elf`、`DbgInfo_*.xz` 等
- **配置文件**：`Android.mk`、`modem_*.mak`、`*.dat` 等
- **数据目录**：`mddata/`（包含证书等数据）
- **其他文件**：根据实际编译产物而定

> **重要提示**：产物仓的内容结构**不固定**，技能会根据实际找到的文件夹内容进行完整复制，不依赖预设的文件列表。

### 产物仓命名规则
| 组成部分 | 说明 | 示例 |
|----------|------|------|
| BOM 名称 | 更新后的 BOM 仓名字 | x6856_h971_a1 |
| 后缀 | -out_vnd | -out_vnd |
| 完整名称 | BOM名称-out_vnd | x6856_h971_a1-out_vnd |

## 目标路径结构

### AP 工程 vendor 路径
```
Z:\U-AP\vendor\mediatek\proprietary\modem\
├── x6856_h971_a1/                   # 复制并重命名后的产物仓
│   ├── config/
│   ├── firmware/
│   ├── include/
│   ├── lib/
│   └── tools/
└── other_bom/                       # 其他项目的产物仓
```

## 复制规则

### 复制方式
使用 Robocopy 命令进行复制，支持：
- 长路径（超过 260 字符）
- 特殊字符文件名
- 文件权限复制
- 重试机制

### Robocopy 参数说明
```
robocopy <源路径> <目标路径> /E /COPYALL /R:3 /W:5 /NP
```

| 参数 | 说明 |
|------|------|
| /E | 复制所有子目录，包括空目录 |
| /COPYALL | 复制所有文件信息（权限、时间戳等） |
| /R:3 | 失败重试次数 |
| /W:5 | 重试等待时间（秒） |
| /NP | 不显示复制进度百分比 |

## 安全检查清单

### 检查项
- [ ] 产物仓文件夹是否存在
- [ ] 目标路径是否存在
- [ ] 目标文件夹是否已存在（需要用户确认覆盖）
- [ ] 磁盘空间是否充足
- [ ] 复制权限是否足够

### 危险操作
- **覆盖已存在的文件夹**：可能导致数据丢失，需要用户确认
- **目标路径不存在**：自动创建路径
- **复制失败**：记录错误信息并通知用户

## 代码规范

### PowerShell 脚本规范
```powershell
# 变量命名：驼峰命名法
$sourceFolder = $null

# 函数命名：动词开头
Function CopyProductRepo {
    param(
        [string]$source,
        [string]$target
    )
    # 函数体
}

# 注释规范
# 单行注释：说明功能
```

### 错误处理规范
```powershell
try {
    # 执行操作
    robocopy $source $target /E /COPYALL
    if ($LASTEXITCODE -gt 7) {
        throw "复制失败"
    }
} catch {
    Write-Error "操作失败：$_"
    return @{ success = $false; message = $_ }
}
```

## 参考资料

- [Robocopy 官方文档](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/robocopy)
- [Android Vendor 目录结构规范](https://source.android.com/docs/core/architecture/vendors)
