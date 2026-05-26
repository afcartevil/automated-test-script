---
funcType: "AI自动化适配"
category: "驱动"
---
﻿---
name: vib-adapt-projectconfig
description: Guides Transsion/MTK linear vibrator macro adaptation by checking vibrator.mk enablement and adding missing macro controls to the matching projects/<project>/ProjectConfig.mk. Use when adapting or debugging LRA/linear vibrator support, Richtap/TikTap macros, vibrator.mk, ProjectConfig.mk, TRAN_RICHTAP_SUPPORT, TRAN_VIB_LIB_NAME, CUSTOM_KERNEL_VIBRATOR, or ro.vendor.vibrator.support.
---

# Transsion LRA Vibrator ProjectConfig

## Scope

Use this skill when the task is to determine whether linear vibrator support is enabled by macro control and, if missing, add the corresponding macro control to the target project's `ProjectConfig.mk`.

Typical source and target:
- Source/reference macro file: `vibrator.mk`
- Target project config: `projects/<project>/ProjectConfig.mk`

## Workflow

1. Identify the target project.
   - Prefer an explicit project name from the user, path, branch context, or opened file.
   - If multiple `projects/<project>/ProjectConfig.mk` files could match, ask the user to choose the project before editing.

2. Locate and read the relevant `vibrator.mk`.
   - Search narrowly first for files named `vibrator.mk`.
   - If the repository is large, search likely module/product areas before doing a full recursive search.
   - Treat `vibrator.mk` as the source of truth for the required macro names and values.

3. Extract vibrator macro controls from `vibrator.mk`.
   - Check for linear/Richtap enablement macros such as:
     - `TRAN_RICHTAP_SUPPORT = yes`
     - `TRAN_VIB_LIB_NAME = libtiktapvibrator`
   - Also check for disable or non-vibrator markers such as:
     - `CUSTOM_KERNEL_VIBRATOR = no`
     - `PRODUCT_ODM_PROPERTIES += ro.vendor.vibrator.support=0`
   - Preserve the exact macro names and values used by the local branch.

4. Inspect the target `ProjectConfig.mk`.
   - Search for existing vibrator-related lines: `VIB`, `vib`, `HAPTIC`, `haptic`, `RICHTAP`, `richtap`, `ro.vendor.vibrator.support`.
   - Do not add duplicates if the macro already exists with the correct value.
   - If conflicting disable markers exist, stop and report the conflict instead of silently overriding them.

5. Add missing linear vibrator macro controls.
   - Place the block near an existing vibrator/haptic section when present.
   - If no such section exists, place it near similar hardware feature macros and keep the edit minimal.
   - Default block when `vibrator.mk` indicates Richtap/TikTap support:

```makefile
# line vibrate
TRAN_RICHTAP_SUPPORT = yes
TRAN_VIB_LIB_NAME = libtiktapvibrator
```

6. Verify after editing.
   - Re-read or search the edited `ProjectConfig.mk` for duplicate/conflicting vibrator macros.
   - Check lints if available.
   - Summarize whether the macro was already enabled or newly added.

## Decision Rules

- If `ProjectConfig.mk` already has `TRAN_RICHTAP_SUPPORT = yes` and the expected `TRAN_VIB_LIB_NAME`, conclude that the project macro control is already enabled.
- If `vibrator.mk` enables linear vibrator support but `ProjectConfig.mk` lacks the corresponding macros, add them.
- If `ProjectConfig.mk` explicitly disables vibrator support, such as `CUSTOM_KERNEL_VIBRATOR = no` or `ro.vendor.vibrator.support=0`, do not change it without confirmation.
- If `vibrator.mk` uses branch-specific macro names, follow those exact names instead of forcing the default Richtap/TikTap block.

## Response Format

Respond in Chinese with:

```markdown
结论：
- [已开启 / 已补充 / 存在冲突需确认]

修改：
- `projects/<project>/ProjectConfig.mk` 中补充/确认的宏控

验证：
- 检查到的关键宏控和是否存在冲突
```
