# 阶段 5：alps/vendor/mediatek/proprietary/custom DWS + 工模 factory.ini

**目标 repo**：`MTK_CODE/alps/vendor/mediatek/proprietary/custom`

## 5A. custom DWS

**目标文件**：`{base_code_sunmao}/vendor/mediatek/proprietary/custom/{project_name_sunmao}/kernel/dct/dct/codegen.dws`

数据源：[references/dws-gpio-rules.md](../references/dws-gpio-rules.md)。

执行步骤同阶段 3 / 4，仅"目标文件"不同。

### 5A 自检（DWS 三处一致性）

阶段 5A 完成后必须把阶段 3 / 4 / 5A 三个目标 DWS 中相同 GPIO 节点的关键字段做一次三方比对：

- 任何一项字段不一致 → 在 checkpoint 中显式给出三处 diff，让开发者定夺。
- 三处完全一致 → 在 checkpoint 中明确写出"3 处 DWS GPIO 配置完全一致"。

## 5B. 工模 `factory.ini`

**目标文件**：`{base_code_sunmao}/vendor/mediatek/proprietary/custom/{project_name_sunmao}/factory/factory.ini`

数据源：[references/factory-ini-rules.md](../references/factory-ini-rules.md)。

### 执行步骤

1. Read 目标文件，确认现有注释风格（`//`）。
2. 按 [factory-ini-rules.md §1](../references/factory-ini-rules.md) 注释 5 个 MenuItem 行；已注释则跳过。
3. 按 [factory-ini-rules.md §2](../references/factory-ini-rules.md) 设置 `Audio.Mic.Sets`：
   - 单麦 → `1`
   - 双麦 → `1,2`
4. 按 [factory-ini-rules.md §3](../references/factory-ini-rules.md) 处理 `Audio.Input.TypecHeadset`：
   - TypeC：确保该行存在且未注释。
   - 3.5mm：注释或不存在。
5. 自检按 [factory-ini-rules.md §4](../references/factory-ini-rules.md)。

### 跳出条款

- 5 个 MenuItem 行有变体（拼写/大小写不同）→ 不要自作主张匹配，问开发者。
- `Audio.Mic.Sets` 出现多次且取值不同 → 问开发者哪一处准。

## 5C. 阶段 5 Checkpoint

| 项 | 内容 |
| --- | --- |
| 本阶段改了什么 | 列出 custom DWS 改动；列出 factory.ini 改动（注释了哪几行、`Audio.Mic.Sets` / `Audio.Input.TypecHeadset` 取值） |
| 还差什么 | 三处 DWS 配置不一致点 / MenuItem 行变体 / 多处冲突 `Audio.Mic.Sets` / factory.ini 编码或换行风格异常 |
| 是否继续 | 默认询问"是否进入阶段 6（验收与交付）？" |
