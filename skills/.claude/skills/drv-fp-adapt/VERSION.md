# DRV_FP_Adapt 版本信息

## 当前版本

- **版本号**：`1.1.6`
- **发布状态**：正式版
- **主 Skill**：[SKILL.md](SKILL.md)
- **主 SOP**：https://transsioner.feishu.cn/wiki/A74wwMGsLiTCBXkMJjVccUDfnKd

## 版本规则

正式版本采用语义化版本号：

- **主版本**（如 `2.0.0`）：主调试流程不兼容变更、适配逻辑重写、主 SOP 范围变化。
- **次版本**（如 `1.1.0`）：新增支持项目场景、新增参考文档、新增适配检查项、扩展输出模板。
- **修订版本**（如 `1.0.1`）：文字修正、路径修正、错别字修复、非行为变更的参考信息更新。

后续若需要先做草稿版或候选版，可使用 `1.1.0-draft`、`1.1.0-rc.1` 等版本号，确认稳定后再发布正式版。

## 发布检查清单

发布新的正式版本前，需确认：

- `SKILL.md` 仍以主 SOP 作为主要调试流程。
- 三个 `EXTENSION_*.md` 文件仍作为参考材料使用。
- 在 [CHANGELOG.md](CHANGELOG.md) 中记录版本号、日期和变更摘要。
- 更新本文件的「当前版本」。
- 更新 [SKILL.md](SKILL.md) 中的「当前版本」。
- 保持 `SKILL.md` 中的 `name` 和 `description` 符合 Cursor Skill 识别要求。

## 文件职责

- `SKILL.md`：主调试流程。
- `REFERENCE.md`：主 SOP 中较长的示例和片段。
- `EXTENSION_CM5.md`：CM5 参考资料。
- `EXTENSION_X6885.md`：X6885 参考资料。
- `EXTENSION_NORMALIZED_SUNMAO.md`：归一化榫卯参考资料。
- `CHANGELOG.md`：版本变更记录。
