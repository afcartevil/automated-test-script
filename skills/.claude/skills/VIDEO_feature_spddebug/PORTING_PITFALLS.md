# 移植常见问题与处理

| 现象 | 原因 | 处理 |
|------|------|------|
| cherry-pick 报 `patch does not apply` | 目标与源分岔大、中间缺提交 | 改 **手工移植**；或先合入依赖 change |
| 同 Change-Id 已在目标 | 以前合过或别的途径进分支 | `git log --grep` 确认；通常 **无需重复移植** |
| 文件仅存在于源路径 | 目录结构因基线不同 | 在目标找等价路径；无等价则与用户确认是否新建 |
| 冲突集中在 `#ifdef` / 平台宏 | 多 SKU / MTK-SPRD 差异 | 保留目标宏骨架，只嵌入源逻辑块 |
| 只改了 .cpp 未改 .h | 源提交漏提或分多个 change | 对照 Gerrit 同主题其它 patchset |
| bp/mk 未移植导致编不过 | 只 pick 了源码 | 同步 `Android.bp` / 依赖模块 |
| sepolicy 拒绝 | 源有新增节点/属性 | 同步 `sepolicy` 与 `file_contexts` |
| 功能仍不对 | 还需 **配置 / prop / overlay** | 查源提交同目录 overlay；问用户要 SPD/配置项 |
| Gerrit 链接 403 | 权限或 VPN | 请用户提供 patch 或 `repo download` |
| 多链接顺序错 | 依赖未满足 | 按 Wiki **依赖** 列重排后重做 |

## 策略选择简表

| 条件 | 建议 |
|------|------|
| 目标已含源 commit 祖先、小 diff | cherry-pick |
| 大范围冲突或路径不同 | 手工按文件移植 |
| 仅需 Wiki 中某提交的部分文件 | 手工 + 在报告注明范围 |
| 源为一系列小提交 | 按依赖顺序逐个 pick，勿 squash（除非用户要求） |

## 禁止事项

- 未读 patch 就声称「已移植完成」  
- 为消冲突而删除目标基线既有定制且无说明  
- 编造 Wiki 中不存在的提交链接
