# 马达 SELinux 功能检查节点清单

节点集合与 **`fc-vib-rootperm`** 相同，见 [../fc-vib-rootperm/nodes.md](../fc-vib-rootperm/nodes.md)。单马达用 `vibrator_single`；双马达对 `vibrator_l`、`vibrator_r` 各跑同一套属性名全表。

## 检查方式

- 每个已存在节点：`ls -lZ`（非 `unlabeled` / `default_t`）
- 仅对各路 **`.../rtp`** 额外 `cat` 试读（`vibrator_single` 或 `vibrator_l`/`vibrator_r` 的 rtp）
- **不查** avc 日志、**不查** `/vendor/etc/vibrator/*.he`

## 标签 Fail 特征

- `unlabeled` / `default_t`
- `rtp` 等 `cat` 返回 `Permission denied`（且 owner 已是 system 时偏 sepolicy）

## 与 DAC 区分

| 现象 | 路由 |
|------|------|
| owner 非 system | `fc-vib-rootperm` |
| owner 为 system，标签/读失败 | sepolicy（参考 `tp-adapt-selinux`） |
