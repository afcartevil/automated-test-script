# patch-analysis-score v1.0.0 部署说明

## 包内容

| 路径 | 说明 |
|------|------|
| `config/` | 评分规则 `scoring-config.yaml`、模块分类 `dev_modules.txt` |
| `docs/patch-analysis/` | 分析流程说明、CHANGELOG、VERSION |
| `tools/` | 分析、HTML 报告、区间索引与 Excel 导出脚本 |
| `web_app/` | Web 服务（可选） |
| `README.md` | CLI 使用说明 |
| `requirements.txt` | Python 依赖 |
| `MANIFEST.txt` | 文件清单与打包时间 |

## 解压到目标仓库

将 **本目录全部内容** 解压到目标项目根目录，保持 `config/`、`tools/` 相对路径不变。

```text
<project-root>/
  config/
  docs/patch-analysis/
  tools/
  README.md
  requirements.txt
  DEPLOY.md
```

## 安装与验证

```bash
pip install -r requirements.txt
python tools/patch_analyzer.py --help
```

## CLI 分析

```bash
python tools/patch_analyzer.py \
  --repo <url> \
  --commit <sha> \
  --config config/scoring-config.yaml \
  --output outputs/out.json

python tools/render_report.py \
  --input outputs/out.json \
  --output outputs/out.html
```

## 注意

- 请保留 `config/` 与 `tools/` 目录，保证配置与脚本版本一致。
- `config/scoring-config.yaml` 可按团队规范修改，建议纳入版本管理。
- 访问 googlesource 可能受速率限制，区间分析建议 `--workers 4~6`、`--chunk-size 50~100`。
