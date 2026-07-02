---
name: product-repo-skill
description: 将 MODEM 产物仓从目标分支公共仓复制到 AP 工程 vendor 路径下。当用户提到 "产物仓创建"、"复制产物仓" 时触发。只做文件夹复制，不修改文件内容。
tools: Glob, Bash
---

# 产物仓创建子技能

## 技能概述
本技能负责将 MODEM 产物仓从目标分支公共仓复制到 AP 工程的 vendor 路径下，完成产物仓的部署。

## 输入参数
| 参数名 | 类型 | 描述 | 必填 |
|--------|------|------|------|
| BOM_Name_Target | string | 更新后的 BOM 仓名字（从 MODEM_SKILL 继承） | 是 |
| Path_B_Pub | string | 目标分支公共仓路径（从 MODEM_SKILL 继承） | 是 |
| AP_Vendor_Path | string | AP 工程 vendor 路径（默认：Z:\U-AP\vendor\mediatek\proprietary\modem） | 是 |

## 输出结果
| 输出项 | 类型 | 描述 |
|--------|------|------|
| success | boolean | 操作是否成功 |
| message | string | 执行结果描述 |
| source_folder | string | 源文件夹路径 |
| target_folder | string | 目标文件夹路径 |
| copied_files_count | integer | 复制的文件数量 |

## 执行流程
1. **接收参数**：接收 BOM_Name_Target、Path_B_Pub、AP_Vendor_Path 参数
2. **询问用户**：询问用户产物是否已编译完成
3. **定位产物仓**：在 Path_B_Pub 下查找包含 "-out_vnd" 的文件夹
4. **验证路径**：检查源文件夹和目标路径是否存在
5. **复制文件夹**：将产物仓复制到 AP_Vendor_Path
6. **重命名文件夹**：将文件夹重命名为 BOM_Name_Target
7. **返回结果**：返回执行结果

## 上下文变量传递
| 变量名 | 来源 | 用途 |
|--------|------|------|
| BOM_Name_Target | MODEM_SKILL | 更新后的 BOM 仓名字，用于查找和重命名文件夹 |
| Path_B_Pub | MODEM_SKILL | 目标分支公共仓路径，用于查找产物仓 |

## 调用方式
```json
{
  "skill_name": "product_repo_skill",
  "action": "execute",
  "parameters": {
    "BOM_Name_Target": "x6856_h971_a1",
    "Path_B_Pub": "Z:\\modem\\S\\99U\\TK_MD_MOLY.NR17.R1.MP3.RC.MP_U0",
    "AP_Vendor_Path": "Z:\\U-AP\\vendor\\mediatek\\proprietary\\modem"
  }
}
```

## 异常处理
1. **产物仓不存在**：提示用户确认产物是否已编译
2. **目标路径不存在**：创建目标路径或提示用户检查路径
3. **文件夹已存在**：提示用户是否覆盖
4. **复制失败**：提示用户检查权限或磁盘空间