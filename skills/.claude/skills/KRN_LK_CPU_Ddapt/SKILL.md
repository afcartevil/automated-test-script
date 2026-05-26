---
name: "cpu-info-adapt-sop"
description: "检查升级前后TRAN_CUSTOMER_SOC_INFO宏控值是否一致，不一致时自动修复。保持文件原有格式。"
funcType: "AI自动化适配"
category: "内核"
---

# CPU信息适配SOP

## 功能描述

该技能用于检查升级前后 `TRAN_CUSTOMER_SOC_INFO` 宏控值是否一致，并在不一致时自动修复，同时保持文件原有格式。

## 使用步骤

### 输入参数

用户需要提供以下信息：
- **升级前分支/路径** (pre_upgrade_source): 升级前的代码来源，可以是OpenGrok分支名或本地路径
- **升级后路径** (post_upgrade_path): 升级后代码的本地目录路径  
- **项目名称** (project_name): 项目名称，如 `cm7_h781`

### 执行流程

1. **第一步：查看升级前tran_projects路径TRAN_CUSTOMER_SOC_INFO的值**
   - OpenGrok路径: `/tran_projects/{project_name}/{project_name}/vendor/mediatek/proprietary/bootable/bootloader/lk2/project/`
   - 本地路径: `{pre_upgrade_path}/tran_projects/{project_name}/{project_name}/vendor/mediatek/proprietary/bootable/bootloader/lk2/project/`
   - 查找对应的mk文件

2. **第二步：如果第一步未找到，则查看升级前vendor路径TRAN_CUSTOMER_SOC_INFO的值**
   - OpenGrok路径: `/vendor/mediatek/proprietary/bootable/bootloader/lk2/project/{project_name}.mk`
   - 本地路径: `{pre_upgrade_path}/vendor/mediatek/proprietary/bootable/bootloader/lk2/project/{project_name}.mk`

3. **第三步：查看升级后TRAN_CUSTOMER_SOC_INFO的值**
   - 检查路径: `{post_upgrade_path}/vendor/mediatek/proprietary/bootable/bootloader/lk2/project/{project_name}.mk`

4. **第四步：对比并处理**
   - 如果升级后的值与升级前一致，返回 `ok`
   - 如果不一致，返回 `false`，并将升级后mk文件中的 `TRAN_CUSTOMER_SOC_INFO` 修改为升级前的值（保持文件原有格式）

### 宏控值格式示例

```
TRAN_CUSTOMER_SOC_INFO := MT6878V_E/ZA
```

### 返回结果

- `ok`: 升级前后宏控值一致
- `false`: 升级前后宏控值不一致，已自动修复

## 修复规则

- 使用字符串替换方式，仅修改宏控值部分，保持文件其他内容不变
- 保留原有注释、换行符和缩进格式
- 使用 `-Raw` 参数读取文件，避免编码问题

## 使用场景

- Android系统升级时的CPU信息适配检查
- 确保升级前后SOC信息配置一致
- 自动化处理mk文件中的宏控值对比和修复

## 示例

**输入**:
- 升级前分支: `tran_mtk_u0.mp1.rc_trunk`
- 升级后路径: `\\10.205.0.143\ziming.zhang1\tOS_od_mtk_A14_trunk`
- 项目名称: `cm7_h781`

**输出**:
- `false`（发现不一致，已修复）
- 修复后值: `TRAN_CUSTOMER_SOC_INFO := MT6878V_E/ZA`