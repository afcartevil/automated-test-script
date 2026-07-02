# 锁卡NV修改子技能执行工作流

## 工作流概述
本工作流定义了锁卡NV修改子技能的详细执行步骤。通过脚本自动判断是否需要修改，无需用户确认。

## 执行步骤

### 步骤1：接收参数
- 从主控技能接收以下参数：
  - Path_B_Pub: 代码B（目标分支）的公共仓路径
  - BOM_Name_Target: 变更后的BOM名称，用于添加宏控

### 步骤2：路径验证
- 检查Path_B_Pub是否存在且可访问
- 若路径无效，返回错误信息给主控技能

### 步骤3：执行修改（使用 LockNvModify.ps1）

```
powershell -ExecutionPolicy Bypass -File "scripts/LockNvModify.ps1" ^
    -TargetBasePath "{Path_B_Pub}" ^
    -BOM_Name_Target "{BOM_Name_Target}"
```

脚本内部逻辑：
1. **预检查**：读取 `mcu/interface/service/nvram/l4_nvram_def.h`
   - 提取 `NVRAM_EF_SUBSIDY_LOCK_LID_VERNO` 的值
   - 如果值为 `"001"` → 跳过所有修改，返回"无需修改"
   - 如果值不为 `"001"` → 继续执行
2. **修改 sml_public_def.h**（10处）
3. **修改 l4_nvram_def.h**（2处）
4. **修改 l4_nvram_editor.h**（3处）

每处修改模式：找到目标宏定义行 → 向下找到第一个 `#if defined(...)` 行 → 在该行末尾添加 `|| defined(__{BOM_Name_Target}__)`

### 步骤4：解析结果
解析脚本返回的JSON输出：
- `skipped=true` → 锁卡NV无需修改（VERNO="001"）
- `skipped=false` → 查看 modifiedCount 和 skippedCount 统计

### 步骤5：返回结果
```json
{
  "success": true,
  "message": "锁卡NV修改完成",
  "skipped": false,
  "subsidyLockLidVerno": "000",
  "modifiedCount": <数量>,
  "skippedCount": <数量>,
  "details": [<修改详情>]
}
```

## C语言宏控修改模式
1. 搜索目标宏定义（如 `#define SML_SL_BLOB_TIME_STAMP_SIZE 8`）
2. 向下查找第一个以 `#if defined(` 开头的条件编译行
3. 在该行末尾追加 `|| defined(__{BOM_Name_Target}__)`
4. 如果该行包含行末注释（`//` 或 `/* */`），宏控添加在注释之前

## 边界情况处理
- **NVRAM_EF_SUBSIDY_LOCK_LID_VERNO="001"**：跳过所有修改，说明当前项目不需要锁卡NV
- **目标宏定义未找到**：跳过该宏定义，记录警告
- **后续无#if defined指令**：跳过该宏定义，记录警告
- **目标文件不存在**：跳过该文件，记录错误
- **文件已包含目标宏控**：跳过该文件，记录信息

## 输出示例

### 示例1：需要修改
```json
{
  "success": true,
  "message": "Lock NV modification completed",
  "subsidyLockLidVerno": "000",
  "modifiedCount": 3,
  "skippedCount": 0,
  "details": [
    { "file": "sml_public_def.h", "changes": 10, "status": "MODIFIED" },
    { "file": "l4_nvram_def.h", "changes": 2, "status": "MODIFIED" },
    { "file": "l4_nvram_editor.h", "changes": 3, "status": "MODIFIED" }
  ]
}
```

### 示例2：无需修改（VERNO="001"）
```json
{
  "success": true,
  "message": "NVRAM_EF_SUBSIDY_LOCK_LID_VERNO value is \"001\", no lock NV modification needed",
  "skipped": true,
  "reason": "Subsidy lock not enabled (VERNO=001)",
  "subsidyLockLidVerno": "001",
  "modifiedCount": 0,
  "skippedCount": 0,
  "details": []
}
```

## 硬约束（必须遵守）
1. **只能用脚本执行**：必须通过 `LockNvModify.ps1` 执行。**禁止**自行构造 Edit、Grep 或其他搜索/修改命令
2. **不读取脚本内容**：直接执行脚本即可，不需要阅读脚本源码
3. **不询问用户是否执行**：脚本会自动判断是否需要修改，无需人工确认
