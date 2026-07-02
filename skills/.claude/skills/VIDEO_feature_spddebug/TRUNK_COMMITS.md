# 主干提交记录（移植用索引）

> **状态：待同步** — 请从飞书 Wiki 导入；**提交链接** 列为移植必需。  
> **来源**：[https://transsioner.feishu.cn/wiki/U4clwnheoiNw52k1txucw8AFnoV](https://transsioner.feishu.cn/wiki/U4clwnheoiNw52k1txucw8AFnoV)  
> **last_synced**：_

## 同步说明

1. 复制 Wiki 中 **主干提交记录** 整表到下方。  
2. **提交链接** 须为可访问的 Gerrit / Git 地址，勿只抄标题。  
3. 多笔移植时保留 Wiki 中的 **顺序 / Depends-On / 备注**。  
4. 同步后删除顶部「待同步」提示。

## 推荐列（与飞书对齐后改表头）

| 列 | 用途 |
|----|------|
| ID | 报告引用，如 `TC-01` |
| 提交链接 | **移植入口**（Gerrit change URL 或 commit URL） |
| Change-Id | `git log --grep` / cherry-pick 链 |
| 标题 | 摘要 |
| 模块 | Media / Display 等 |
| 源分支 | 提交所在 trunk（如 `tOS_mtk_A16_trunk`） |
| 依赖提交 | 须先移植的链接或 ID |
| 备注 | 适配说明、已知冲突文件 |

## 提交记录表

| ID | 提交链接 | Change-Id | 标题 | 模块 | 源分支 | 依赖 | 备注 |
|----|----------|-----------|------|------|--------|------|------|
| _示例_ | _https://gerrit.../c/xxx/+/_ | _Ixxxx_ | _subject_ | _Video_ | _tOS_mtk_A16_trunk_ | _无_ | _ |

## 按 ID 快速取链（同步后填写）

```text
# TC-01: <url>
# TC-02: <url>
```
