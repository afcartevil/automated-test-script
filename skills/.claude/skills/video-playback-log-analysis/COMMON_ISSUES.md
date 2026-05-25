# 常见问题与原因对照表

| 问题现象 | 日志特征 | 根因 | 责任域 | 建议 |
|---|---|---|---|---|
| 超 spec 导致播放异常 | `E MediaCodec: Codec reported err 0xffffffea/BAD_VALUE, actionCode 0, while in state 3/CONFIGURING` | 片源超 spec | 片源 | 检查视频编码参数、分辨率、profile/level 是否超过平台能力 |
| 解码器创建失败 | `D C2MtkComponentStore: onNumberOfVideoInstancesChanged: Decoder 16, Encoder 1` | 创建解码器数量达到 max | 系统资源/应用行为 | 排查是否有其他 app 异常创建大量解码器且不释放 |
| 平台解码异常 | `E VPUD : [MP4_DEC] ERROR: VOP_START_CODE_(0x1B6) not found!!` | 平台问题 | 平台/MTK | 整理日志并联系 MTK 分析 |
| 应用问题 | 未创建解码器 | 应用问题 | app | 检查应用是否真正发起视频解码流程 |
| 录屏失败或配置失败 | `E MediaCodec: Codec reported err 0xffffffea/BAD_VALUE, actionCode 0, while in state 3/CONFIGURING` 且 `configure failed with err 0xffffffea, resetting...` | 录屏下发参数异常，编码器创建失败 | app/框架 | 检查录屏参数配置是否合法 |

## 快速判断规则

- 看到 `BAD_VALUE`：优先怀疑参数异常或片源超 spec。
- 看到 `Decoder 16, Encoder 1`：优先怀疑解码器实例数达到上限。
- 看到明确 `VPUD` 错误：优先归类为平台问题。
- 从头到尾没有创建解码器：优先归类为应用问题。
- 没有任何异常日志：当前日志无效，建议重新抓取。
