# 参考提交（Gerrit topic）

下列 4 个项目都已经走完一次 Audio P1 bringup。**只读参考**，不替开发者复述补丁、不抄袭代码。

| 项目 | Gerrit topic | 链接 | 升级场景 |
| --- | --- | --- | --- |
| cm7 | `cm7w_audio_bring_up` | <https://gerrit.transsion.com/q/topic:cm7w_audio_bring_up> | 待开发者补全 |
| x6873 | `x6873w_audio_bring_up` | <https://gerrit.transsion.com/q/topic:x6873w_audio_bring_up> | 待开发者补全 |
| x6885 | `x6885_audio_p1` | <https://gerrit.transsion.com/q/topic:x6885_audio_p1> | 待开发者补全 |
| lj7 | `lj7w_audio_bringup` | <https://gerrit.transsion.com/q/topic:lj7w_audio_bringup> | 待开发者补全 |

## 阅读指引

不要把这些 topic 当成"标准答案抄一遍"，每个项目都有自己的板级差异（I2C 总线 / GPIO 号 / PA 型号 / typec switch）。建议按下表用法读：

| 问题场景 | 推荐参考 | 怎么读 |
| --- | --- | --- |
| 不确定某宏控该写什么 | 任一同 PA 型号项目 | 看其 `ProjectConfig.mk` 对应宏控值，**仅作 sanity check**，最终值仍以 [projectconfig-macros.md](../references/projectconfig-macros.md) 三级 fallback 为准 |
| 不确定 `tran_audio_controller` 节点结构 | 同平台同 typec 类型项目 | 看其 DTS 节点的属性集合，按 [dts-node-templates.md](../references/dts-node-templates.md) 校对 |
| 不确定 audio_device.xml 项目层叠加方式 | 同平台项目 | 看其 audio_device.xml diff（项目层 vs 平台层），观察叠加风格 |
| vnd12→vnd16 的 rv/hifi3 xml 缺源 | x6885 / lj7（如适用） | 看其是否曾从 AFE 拉取过新版本，作为开发者咨询 AFE 时的旁证 |

## 风险提示

- topic 中的补丁可能包含 **该项目特有 hack**（如某 GPIO 因板级问题改向、某宏控因功能裁剪强制 `no`）；**不要无脑套用**。
- topic 中如有 `test-aware` 风格的分支（按 UID / 包名做差异化处理） → **绝对不要复制**，违反 GMS 红线。
- topic 中的 PA so / bin 文件二进制变更不能跨项目复制——必须按本 SKILL 的 PA 文件矩阵从本项目升级前路径取。

## 维护

- 后续每完成一个新项目的 P1 bringup，建议把项目名 / Gerrit topic 补充到本表，便于横向对照。
- 老项目升级场景（vnd12 非榫卯 / vnd14 非榫卯）应在"升级场景"列里标明，避免后续混用。
