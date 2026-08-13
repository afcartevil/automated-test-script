# DRV_FP_Check 版本信息

## 当前版本

- **版本号**：`1.3.0`
- **发布状态**：正式版
- **主 Skill**：[SKILL.md](SKILL.md)
- **检查规则**：[CHECK_ITEMS.md](CHECK_ITEMS.md)
- **参考格式**：`DRV_FP_Adapt`

## 版本规则

正式版本采用语义化版本号：

- **主版本**（如 `2.0.0`）：检查流程不兼容变更、判断规则重写、适用范围发生明显变化。
- **次版本**（如 `1.1.0`）：新增检查项、新增项目场景、新增输出字段、扩展检查规则。
- **修订版本**（如 `1.0.1`）：文字修正、路径修正、错别字修复、非行为变更的说明更新。

后续若需要先做草稿版或候选版，可使用 `1.1.0-draft`、`1.1.0-rc.1` 等版本号，确认稳定后再发布正式版。

## 发布检查清单

发布新的正式版本前，需确认：

- `SKILL.md` 仍保持只读检查优先，不在用户未要求时主动修改文件。
- [CHECK_ITEMS.md](CHECK_ITEMS.md) 覆盖当前版本声明的所有检查项。
- 在 [CHANGELOG.md](CHANGELOG.md) 中记录版本号、日期和变更摘要。
- 更新本文件的「当前版本」。
- 更新 [SKILL.md](SKILL.md) 中的「当前版本」。
- 保持 `SKILL.md` 中的 `name` 和 `description` 符合 Cursor Skill 识别要求。

## 文件职责

- `SKILL.md`：主检查流程、使用边界、输出模板。
- `CHECK_ITEMS.md`：指纹 rc/xml、DTS/DWS、`tran-keys`、驱动 compatible；人脸 HAL 初始化、服务、算法版本的详细判断规则。
- `VERSION.md`：版本号、发布规则和发布检查清单。
- `CHANGELOG.md`：版本变更记录。
