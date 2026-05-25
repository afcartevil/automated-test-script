**概述**
- **目标**：依照飞书《安全 AI调试SOP》，为 `android-platform-security-upgrade-ai-debug` Skill 制作可执行的使用 SOP，覆盖 DA、防回滚、BROM、AVB、RPMB 的移植与核对流程。
- **输出**：一份可直接使用的检查表与操作步骤，及最终的报告模板（便于提交审核）。

**适用范围**
- 角色：平台安全驱动工程师
- 代码形态：MTK bootloader（preloader、lk2）与 Tran 项目配置（vendor/transsion/projects/...）

**输入与前置条件**
- 用户必须提供：`pre_branch_path`/`branch_before`、`post_branch_path`/`branch_after`、`project_name`、`platform_name`。
- 可选但建议：`device_product_dir`、衍生项目列表。
- 必备：升级前后源码可读或可 diff，升级后 `ProjectConfig.mk` 与目标 dts 可定位。

**操作步骤（逐项执行、项目优先）**
1. 确认策略与路径
- 确认仅移植安全相关配置，且**项目配置覆盖平台配置**。
- 确定并记录输入：项目名、平台名、升级前后基线（路径或 git ref）。

2. 读取升级前目标值（参照 KEYWORDS）
- 查找并记录下列项的升级前值：
  - `TRAN_DA_ANTI_ROLLBACK_VER`（DA）
  - `TRAN_BLOW_DISBROM_SUPPORT`（BROM）
  - preloader/lk2 中的软件防回滚宏与 `anti_ver.json` 项目版本
  - `TRAN_AVB_REMOTE_SIGN_SUPPORT`（AVB）
  - RPMB 相关：dts 中 `tran,rpmb_control`、preloader/ProjectConfig 的宏

3. 在升级后对齐项目侧（按项目优先）
- DA：保持 `TRAN_DA_ANTI_ROLLBACK_VER` 与升级前一致，写入升级后项目 mk（仅项目 mk）。
- BROM：按升级前值设置 `TRAN_BLOW_DISBROM_SUPPORT`，仅修改升级后 lk2 项目 mk。
- 软件防回滚：在 preloader/lk2 中对齐宏，并在 `anti_ver.json` 中保证项目条目与版本一致；若衍生项目缺项，则补配。
- AVB：在 `vendor/transsion/projects/<product>/ProjectConfig.mk` 或项目对应路径对齐 `TRAN_AVB_REMOTE_SIGN_SUPPORT`。
- RPMB：对齐 dts（`&mobicore`）、preloader 宏及 ProjectConfig 中的 `TRAN_RPMB_SUPPROT` 等。

4. 校验与输出报告
- 回读升级后代码，确保目标值已正确写入并在预期文件中存在。
- 生成报告，使用下列模板片段（见“输出模板”）。

5. 异常与人工确认点
- 若找不到 `ProjectConfig.mk` 或目标文件路径不明确，记录并请项目负责人确认目录命名。
- `anti_ver.json` 若无衍生条目且存在继承关系：按 SOP 补配并标注风险。
- 对 DA/BROM 无明确定义时停止并人工确认。

**常用命令示例**
```bash
# 在本地路径上对比升级前后（示例）
git --no-pager diff --name-only <pre_ref> <post_ref> | grep -E "preloader|lk2|ProjectConfig|anti_ver.json|dts"
# 查询某宏在仓库中的定义
grep -R "TRAN_DA_ANTI_ROLLBACK_VER" <repo_root> || true
```

**输出模板（建议保存为 markdown）**
- 保存位置建议：`SOP.md` 与最终报告并置在同一 skill 目录下。
- 报告结构（摘要）：
  - 基本信息：SOP 链接、项目名、平台名、升级前后基线
  - 修改文件清单：文件路径 / 变更类型 / 对应能力
  - 配置对齐表：能力 / 宏或配置项 / 升级前目标值 / 升级后结果 / 说明
  - 衍生项目与风险、提交建议

**参考与扩展**
- 请参阅 Skill 源文件：[SKILL.md](SKILL.md)、[ANALYSIS_STEPS.md](ANALYSIS_STEPS.md)、[KEYWORDS.md](KEYWORDS.md)、[COMMON_ISSUES.md](COMMON_ISSUES.md)。

---
简短检查表（可打印）
- [ ] 已获取 `pre_branch_path` 与 `post_branch_path`
- [ ] 已记录 `project_name` 与 `platform_name`
- [ ] 已导出升级前目标值（DA/BROM/anti_ver/AVB/RPMB）
- [ ] 已在升级后项目侧完成对齐并提交修改清单
- [ ] 已生成并提交报告
