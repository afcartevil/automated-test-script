# RF参数项目目录结构（真实示例）

## 重要：RF参数项目目录 ≠ 只有 mcu 文件夹

RF参数项目目录下包含**根级配置文件** + **mcu子目录**，两者都必须完整复制。

## 真实项目目录结构示例

### 示例：x6850_h895_f1_v 项目

```
x6850_h895_f1_v/
│
├── TK_MD(LWCG_R2_6789).ini    ← 根级配置文件，必须复制
├── TMDK.cfg                   ← 根级配置文件，必须复制
│
└── mcu/
    ├── custom/
    │   └── l1/
    │       └── cl1_rf/
    │           ├── MT6789_C2K_MT6186M_CUSTOM/
    │           │   ├── c2k_custom_drdi.c
    │           │   ├── c2k_custom_drdi.h
    │           │   ├── DRDI/
    │           │   │   └── Set0/
    │           │   │       └── ... (大量 .bin/.c/.h 文件)
    │           │   └── ... (更多 .c/.h 文件)
    │           └── ... (更多 RF 平台目录)
    └── ... (mcu 下更多子目录和文件)
```

## 根级文件清单（必须检查）

| 文件类型 | 文件名模式 | 说明 | 位置 |
|---------|-----------|------|------|
| .ini | `TK_MD(*).ini` | Modem配置文件，包含RF版本等关键信息 | 项目目录根级 |
| .cfg | `TMDK.cfg` | Transsion Modem Dev Kit配置 | 项目目录根级 |

**这些根级文件不在 mcu/ 目录下**，如果只复制 mcu/ 会丢失这些文件。

## RF_TARGET_LOCATION 目标路径映射表

| RF_TARGET_LOCATION 值 | 目标路径 | 示例 |
|----------------------|---------|------|
| `public` | `{Path_B_Pub}\projects\{BOM_Name_Target}` | `Z:\modem\S\new95\TK_MD_MOLY.NR17.R1.MP3.RC.MP_U0\projects\x6850_h895_f1_v` |
| `private` | `{Path_B_Priv}\projects\{BOM_Name_Target}` | `Z:\modem\S\new95\Tran_modem_S\projects\x6850_h895_f1_v` |

**禁止行为**：
- 禁止无视 RF_TARGET_LOCATION 自行选择目标仓
- 禁止使用 Path_B_Pub / Path_B_Priv 之外的任何其他路径
- 如果 RF_TARGET_LOCATION = `public`，目标路径**必须包含 Path_B_Pub**
- 如果 RF_TARGET_LOCATION = `private`，目标路径**必须包含 Path_B_Priv**

## 搜索顺序说明

RfSearch.ps1 脚本按以下 4 步顺序搜索：

```
步骤1: {Path_A_Pub}/projects/*.json     → 找到BOM_Name对应条目则返回
步骤2: {Path_A_Priv}/projects/*.json    → 步骤1未找到时执行，找到则返回
步骤3: {Path_A_Pub}/projects/ 目录grep → 步骤2未找到时执行，找到则返回
步骤4: {Path_A_Priv}/projects/ 目录grep → 步骤3未找到时执行，找到则返回

全部未找到 → 报错 "未找到BOM名称为 {BOM_Name} 的项目文件夹"
```

**关键点**：
- 步骤1 未找到 ≠ 搜索结束，必须继续步骤 2、3、4
- 只有步骤 1~4 全部未找到时才报错
- RfSearch.ps1 脚本内部已实现上述4步，直接调用即可

## 复制完整性验证

复制完成后必须验证以下项全部存在：

```
✅ .ini 文件在目标路径根级存在（如 TK_MD(LWCG_R2_6789).ini）
✅ .cfg 文件在目标路径根级存在（如 TMDK.cfg）
✅ mcu/ 目录完整复制到目标路径
✅ 源文件总数 = 目标文件总数
```
