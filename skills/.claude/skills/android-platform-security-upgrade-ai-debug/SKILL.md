---
name: android-platform-security-upgrade-ai-debug
description: 针对手机大版本升级中平台安全相关功能移植与核对，覆盖 DA 动态防回滚、BROM 端口禁用、软件防回滚（preloader/lk2 宏与 anti_ver.json）、AVB 在线签名（TRAN_AVB_REMOTE_SIGN_SUPPORT）、实体 RPMB（dts/preloader/project）。在用户给出升级前与升级后代码基线及项目名、平台名时，按项目配置优先于平台配置的规则读取升级前目标值，在升级后对齐项目侧（及 SOP 要求的 dts、anti_ver.json、ProjectConfig）并输出修改文件与功能配置摘要。当用户引用飞书安全 AI 调试 SOP 或进行 MTK+Tran 树安全移植排查时使用。
disable-model-invocation: true
---

# 平台安全升级 AI 调试（飞书 SOP 对齐）

依据组织《安全 AI调试SOP》（[飞书文档](https://transsioner.feishu.cn/docx/JIq0dLEfHopv90xzzDScU7RFnTb)）：**仅移植平台安全相关能力**；默认规则为**项目配置覆盖平台配置**；升级后 **DA/BROM 仅改项目 mk**，其余项按 SOP 在指定文件中修改。

## 适用范围

- **角色**：平台安全驱动工程师在大版本升级中做安全侧移植与 AI 辅助核对。
- **软件形态**：MTK bootloader 树（preloader、lk2）+ Tran 项目配置（`vendor/transsion/projects/...`）+ 可选 kernel dts；路径以用户仓库为准，下表为 SOP 给定模板。

## 输入（必须由用户提供）

| 参数 | 说明 |
|------|------|
| `pre_branch_path` 或 `branch_before` | 升级前本地路径或 Git 引用 |
| `post_branch_path` 或 `branch_after` | 升级后本地路径或 Git 引用 |
| `project_name` | 与 `preloader/custom` 目录名一致 |
| `platform_name` | 芯片平台名（用于 platform 目录段） |

可选：`device_product_dir`（升级前 `device/transsion/<product>/` 等，便于定位 `ProjectConfig_BSP.mk`）、衍生项目列表（如 x6885b 继承 x6885）。

## 前置条件

| 输入/材料 | 必需性 | 用途 |
|-----------|--------|------|
| 升级前、升级后可读源码树或可对两引用做 diff | 必需 | 读取宏与 JSON |
| `project_name`、`platform_name` | 必需 | 拼接 SOP 路径 |
| 升级后目标 `ProjectConfig.mk` 路径（或可由项目名推断） | AVB/RPMB 必需 | Tran 侧宏 |
| 升级后项目对应 dts 路径 | RPMB 必需 | `tran,rpmb_control` |

## 移植内容总览（与 SOP 一致）

1. **DA 动态防回滚**：`TRAN_DA_ANTI_ROLLBACK_VER`，与升级前一致；平台/项目路径见 [KEYWORDS.md](KEYWORDS.md)。
2. **BROM 端口禁用**：`TRAN_BLOW_DISBROM_SUPPORT`（yes/no），与升级前一致；**仅改升级后 lk2 项目 mk**。
3. **软件防回滚**：preloader/lk2 固定宏 + `anti_ver.json` 中项目版本号与升级前一致；**所有项目需导入**；注意衍生项目继承与补配。
4. **AVB 在线签名**：`TRAN_AVB_REMOTE_SIGN_SUPPORT`，与升级前一致；升级后通常在 `vendor/transsion/projects/<product>/ProjectConfig.mk`。
5. **实体 RPMB**：dts `&mobicore`、preloader RPMB/TEE 宏、project 侧 `TRAN_RPMB_SUPPROT` / `TRAN_ENABLE_RPMB_FACTORY_SUPPORT`；是否导入可参考升级前 `TRAN_ENABLE_RPMB=yes`（SOP 示例）。

## 执行工作流（概述）

```text
移植/调试进度：
- [ ] 步骤1：确认策略（仅安全、项目优先覆盖平台）并解析路径
- [ ] 步骤2：DA 与 BROM：读升级前项目→平台，定目标值；仅写升级后项目 mk
- [ ] 步骤3：软件防回滚：对齐 preloader/lk2 宏与 anti_ver.json；处理衍生项目
- [ ] 步骤4：AVB：对齐升级后 ProjectConfig 中 TRAN_AVB_REMOTE_SIGN_SUPPORT
- [ ] 步骤5：RPMB：按升级前门控对齐 dts、preloader、ProjectConfig
- [ ] 步骤6：回读校验并按模板输出
```

详细分步、判断表与命令示例见 [ANALYSIS_STEPS.md](ANALYSIS_STEPS.md)。

## 输出格式

按以下模板输出（便于评审与提交）：

```markdown
# 平台安全升级 AI 调试报告

## 基本信息
- SOP：[安全 AI调试SOP](https://transsioner.feishu.cn/docx/JIq0dLEfHopv90xzzDScU7RFnTb)
- 项目名：<project_name>，平台名：<platform_name>
- 升级前基线：<path 或 ref>
- 升级后基线：<path 或 ref>

## 一、修改了哪些文件
| 文件路径 | 变更类型（新增/修改/仅核对） | 对应能力 |
|----------|------------------------------|----------|
| ... | ... | DA / BROM / 软件防回滚 / AVB / RPMB |

## 二、配置了哪些功能
| 能力 | 宏或配置项 | 升级前目标值 | 升级后结果 | 说明 |
|------|------------|--------------|------------|------|
| DA 防回滚 | TRAN_DA_ANTI_ROLLBACK_VER | | | 来源：项目优先 |
| BROM 禁用 | TRAN_BLOW_DISBROM_SUPPORT | | | yes/no |
| 软件防回滚 | MTK_SECURITY_ANTI_ROLLBACK 等 | | | preloader/lk2 |
| 软件防回滚 | anti_ver.json 项目项 | | | 版本号一致 |
| AVB 在线签名 | TRAN_AVB_REMOTE_SIGN_SUPPORT | | | |
| RPMB | dts / preloader / project | | | 见 SOP 片段 |

## 三、衍生项目与风险
- 衍生项目补配：<列表或「无」>
- 待人工确认：<dts 实际文件名、ProjectConfig 路径等>

## 四、提交建议
- 标题建议：`security: align platform security porting for <project_name> (SOP)`
- 说明要点：仅安全相关；DA/BROM 仅项目 mk；anti_ver/AVB/RPMB 按 SOP 路径
```

## 异常处理

- 升级后项目 mk 或 `ProjectConfig.mk` 不存在：列出尝试路径，请用户确认目录命名（如 `lk6_h582`）。
- `anti_ver.json` 无衍生项目条目但存在继承关系：按 SOP 在升级后**增加**衍生项目配置。
- 平台与项目均未定义某宏：对 DA/BROM 报错停止；其余项按 SOP 是否“所有项目导入”处理。

## 参考资源

- 宏、路径与检索用关键字：[KEYWORDS.md](KEYWORDS.md)
- 逐步操作与判断：[ANALYSIS_STEPS.md](ANALYSIS_STEPS.md)
- 常见问题：[COMMON_ISSUES.md](COMMON_ISSUES.md)
- 案例：[CASES.md](CASES.md)

## 与其它 Skill 的关系

仓库内 `platform-security-upgrade-porting` 仅覆盖 **DA + BROM**；本 Skill 与飞书 SOP **全文一致**，包含软件防回滚、AVB、RPMB。若任务仅两项安全配置，可改用较窄 Skill 以减少范围。
