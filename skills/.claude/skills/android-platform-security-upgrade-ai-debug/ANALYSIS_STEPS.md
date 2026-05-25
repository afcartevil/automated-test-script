# 详细分析/移植步骤（忠实还原飞书 SOP 流程）

SOP：[安全 AI调试SOP](https://transsioner.feishu.cn/docx/JIq0dLEfHopv90xzzDScU7RFnTb)

## 通用原则

| 原则 | 说明 |
|------|------|
| 范围 | 只处理平台安全相关移植 |
| 覆盖顺序 | 读宏时：**先项目配置，再平台配置**（项目覆盖平台） |
| 写策略 | **DA、BROM**：升级后 **只修改项目 mk**；平台 mk 仅只读对照 |
| 软件防回滚 | **所有项目**均需导入；需同时改 preloader、lk2、`anti_ver.json` |

---

## 步骤 A：DA 动态防回滚

### 目标

`TRAN_DA_ANTI_ROLLBACK_VER` 在升级后与升级前**一致**（仅关心版本号取值）。

### 操作

1. 升级前：在 **项目** `preloader/custom/(project)/(project).mk` 查找该宏。
2. 若项目无定义，则在 **平台** `preloader/platform/(platform)/default.mak` 查找。
3. 记录目标值（保持原文格式，不擅自改进制）。
4. 升级后：读取项目、平台当前值；**仅编辑升级后项目 mk**，将宏设为升级前目标值。

### 判断

| 条件 | 结论 |
|------|------|
| 升级前项目与平台均无该宏 | 报错停止，需人工确认升级前基线 |
| 升级后项目已等于目标值 | 标记无需修改 |
| 升级后项目缺失或与目标不一致 | 新增或更新项目 mk |

---

## 步骤 B：BROM 端口禁用

### 目标

`TRAN_BLOW_DISBROM_SUPPORT` 为 **yes** 或 **no**，与升级前一致。

### 操作

同「项目优先、平台兜底」读取升级前目标值；**仅修改升级后** `lk2/project/(project).mk`。

### 判断

| 条件 | 结论 |
|------|------|
| 目标值不是 yes/no | 报错停止 |
| 升级后已一致 | 无需修改 |

---

## 步骤 C：软件防回滚

### 目标

- preloader、lk2 宏与 SOP 给定一致（见 [KEYWORDS.md](KEYWORDS.md)）。
- `anti_ver.json` 中**对应项目的防回滚版本号**与升级前一致。
- 处理 **衍生项目**：如 x6885b 继承 x6885，升级前分支可能无独立项，升级后需**补配置**。

### 操作

1. 导出升级前 `anti_ver.json` 中与该项目（及父项目）相关的版本条目。
2. 在升级后 `anti_ver.json` 中对齐同一逻辑版本；缺衍生项目则新增。
3. 在升级后 preloader、lk2 项目 mk 中写入 SOP 要求的宏（若已有则校验取值与 export/`:=` 风格）。

### 判断

| 条件 | 结论 |
|------|------|
| 升级后缺少衍生项目键 | 按继承关系补全 |
| JSON 版本号与升级前不一致 | 修改为升级前目标 |

---

## 步骤 D：AVB 在线签名

### 目标

`TRAN_AVB_REMOTE_SIGN_SUPPORT` 与升级前一致。

### 操作

1. 在升级前 `ProjectConfig_BSP.mk`（或用户给出的 Tran device 路径）读取该宏。
2. 在升级后 `vendor/transsion/projects/<product>/ProjectConfig.mk`（或用户确认路径）写入相同取值。

### 判断

| 条件 | 结论 |
|------|------|
| 升级后找不到 ProjectConfig | 列出搜索路径请用户确认 product 目录名 |

---

## 步骤 E：实体 RPMB

### 目标

dts、`preloader` 项目 mk、`ProjectConfig.mk` 与升级前策略一致；SOP 示例：**若升级前 `TRAN_ENABLE_RPMB=yes` 则导入 RPMB**。

### 操作

1. 读升级前 `ProjectConfig_BSP.mk` 中 `TRAN_ENABLE_RPMB`（及 SOP 列出的其它 RPMB 相关宏）。
2. 若需导入：在升级后 dts 增加/核对 `&mobicore { tran,rpmb_control = <1>; };`。
3. Preloader 项目 mk：对齐 `CFG_RPMB_SET_KEY`、`CFG_RPMB_KEY_PROGRAMED_IN_KERNEL`、`CFG_TEE_SUPPORT` 及 export。
4. 升级后 `ProjectConfig.mk`：对齐 `TRAN_RPMB_SUPPROT`、`TRAN_ENABLE_RPMB_FACTORY_SUPPORT`（拼写以 SOP 为准）。

### 判断

| 条件 | 结论 |
|------|------|
| 升级前未启用 RPMB | 不强制写入 RPMB 块（以升级前门控为准） |
| dts 路径因内核版本变化 | 以实际 `arch/arm64/boot/dts/mediatek/` 下项目 dts 为准 |

---

## 步骤 F：汇总与校验

1. 回读所有已修改文件中的目标宏与 JSON 片段。
2. 确认未修改升级后 **DA/BROM 的平台侧** default.mak / rules.mk（与 SOP「只对项目配置文件进行修改」一致）。
3. 按 `SKILL.md` 输出模板生成报告。
