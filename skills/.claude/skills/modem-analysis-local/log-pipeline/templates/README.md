# templates/

Samba 发布成功后追加 Jira 评论的模板目录。

## 文件

- `jira_publish_comment.template.example` — 示例模板。**复制一份**改成你想要的格式，再在 `.env` 里指向它：

```
JIRA_COMMENT_AFTER_PUBLISH=1
JIRA_PUBLISH_COMMENT_TEMPLATE=templates/jira_publish_comment.template.example
```

## 模板语法

- 编码：**UTF-8**
- 语法：Python `string.Template`
- 占位符用 **`$name`**（不要用 `{name}`，避免和路径里的花括号或单纯文本混淆）
- **没有注释语法** — 文件里的每个字符都会出现在最终评论里。需要写说明请放到本 README

### 可用占位符

| 占位符 | 含义 |
|---|---|
| `$issue_key` | Jira 单号 |
| `$smb_zip_rel` | 共享内 zip 相对路径（正斜杠），如 `通信开发部/AI2D-log/2026-05-22/OS162-37733.zip` |
| `$unc_base` | zip 文件完整 UNC |
| `$publish_date` | 发布日期目录 `YYYY-MM-DD` |
| `$published_at` | 发布完成 ISO-8601 时间 |
| `$robocopy_exit` | robocopy 退出码（字符串） |
| `$phase1_host` | 执行 Phase 1 的 Windows 主机名 |
| `$manifest_path` | 本地 `job_manifest.json` 绝对路径 |
| `$robocopy_mode` | 固定 `robocopy /MIR` |

未知占位符（如打错字）会原样保留，不会让发评论失败。

## 自测

```powershell
# 用真实 manifest 渲染，但不发 Jira
python pipeline_steps\jira_post_publish_comment.py `
  --manifest "D:\modem_pipeline_work\OS162-37733\job_manifest.json" --dry-run
```
