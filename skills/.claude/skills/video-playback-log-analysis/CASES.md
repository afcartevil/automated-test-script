# 典型案例

## 案例1：起播失败

### 现象

- whatsapp 播放视频失败

### 根因

- 其他 app 异常创建大量解码器不释放，导致解码器数量达到 max，whatsapp 创建解码器失败

### 关键日志

```text
01-29 16:02:22.827205 1425 17840 D C2MtkComponentStore: onNumberOfVideoInstancesChanged: Decoder 16, Encoder 1
```

### 分析要点

- 问题不一定出在当前播放 app。
- 需结合全局解码器实例数判断是否存在资源被其他 app 占满。

## 案例2：录屏失败

### 现象

- 手机录制功能录屏失败

### 根因

- 录屏下发参数异常，编码器创建失败

### 关键日志

```text
E MediaCodec: Codec reported err 0xffffffea/BAD_VALUE, actionCode 0, while in state 3/CONFIGURING
E MediaCodec: configure failed with err 0xffffffea, resetting...
```

### 分析要点

- 问题发生在配置阶段。
- 重点检查录屏相关参数是否合法。

## 使用这些案例的方式

- 当日志特征与案例高度相似时，可快速复用对应归因思路。
- 最终结论仍需以当前日志中的直接证据为准。
