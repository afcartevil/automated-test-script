# 变更边界矩阵

## 仅对比（禁止修改）

- `workflows/audio-macro-check.md`
- `workflows/dolby-self-check.md`
- `workflows/ringtone-check.md`
- `workflows/dts-self-check.md` 的 2.1 submix 通道检查部分

## 允许修改（受限）

- `workflows/dts-self-check.md` 的 2.2 参数路径检查：
  - 仅允许在 `customer.cfg` 末尾追加 `tuningPath=/odm/etc/asset/audio/dts`
- `workflows/pa-path-check.md`：
  - 仅允许修改指定节点下的 `param_path`

## 通用限制

- 所有允许修改场景都必须记录到“改动项”中。
- 禁止改动 workflow 未明确允许的字段。
