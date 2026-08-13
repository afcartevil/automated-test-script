---
name: bsp-adapt-holster-hall
description: >-
  Verifies or edits `TRAN_BSP_HOLSTER_HALL_SUPPORT` in Transsion project
  `ProjectConfig.mk` to enable or disable the factory (工模) holster hall item.
  Use when porting a project, enabling/disabling 皮套霍尔、霍尔工模、hall sensor
  factory test, or when the user names `TRAN_BSP_HOLSTER_HALL_SUPPORT` or
  `ProjectConfig.mk` under `transsion/projects`.
disable-model-invocation: true
funcType: "AI自动化适配"
category: "驱动"
---

# Transsion：皮套霍尔与 `ProjectConfig.mk`

## Scope

- **File**: `vendor/transsion/projects/<project>/ProjectConfig.mk` (tree layout may appear as `vendor/vendor/transsion/projects/<project>/ProjectConfig.mk`; resolve `<project>` from the task or user-provided name).
- **Symbol**: `TRAN_BSP_HOLSTER_HALL_SUPPORT` — enables BSP holster hall support used by the factory/midtest holster hall flow.

## Check

1. Open the target project’s `ProjectConfig.mk`.
2. Search for `TRAN_BSP_HOLSTER_HALL_SUPPORT`.
3. **Present**: value must be `yes` to turn the feature on; if set to `no` or commented out inconsistently, treat as disabled unless product policy says otherwise.

## Add (需要皮套霍尔工模项)

When hardware **has** a holster/cover hall sensor and the product needs the factory item:

1. If the line is **missing**, add a block near other BSP/USD feature flags (same style as sibling projects), for example:

```makefile
#USD:add hall by <owner> <date> start
TRAN_BSP_HOLSTER_HALL_SUPPORT = yes
#USD:add hall by <owner> <date> end
```

2. Use `= yes` with spaces around `=` to match existing `ProjectConfig.mk` conventions in this tree.

## Remove (不需要或硬件无霍尔)

When the platform **does not** use holster hall in factory, or hardware drops the hall:

1. Remove the **assignment** `TRAN_BSP_HOLSTER_HALL_SUPPORT = yes` (and matching `#... start/end` comments if they only wrap this symbol).
2. Do **not** leave a stray `= no` unless the build system for this branch explicitly requires an explicit `no`; prefer full removal if other projects omit the symbol entirely.

## Output

Summarize for the user:

- Path edited and whether the symbol is now **present + yes** or **removed**.
- One-line rationale (need / no need factory item, hardware).

## Constraints

- Only touch the relevant project’s `ProjectConfig.mk` unless the user asks to align multiple projects.
- Do not change unrelated `TRAN_*` or MTK macros in the same edit.
