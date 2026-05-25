# 关键字与日志示例

## 关键词列表

可直接用于搜索的关键词：

- `Mediacodec`
- `Number of i`
- `returned error: 0xe`
- `vpud`
- `C2MtkVdec`
- `Codec reported err`

## 关键日志示例与解读

### 1. 解码器创建

```text
15311:04-16 15:33:34.782 23653 28237 D MediaCodec: CreateByComponentName: name c2.mtk.vp9.decoder
15321:04-16 15:33:34.784 23653 28260 D MediaCodec: [0xb400007489aed670] setState: 1
15357:04-16 15:33:34.800 23653 28261 I CCodec  : Created component [c2.mtk.vp9.decoder]
```

字段解读：
- `CreateByComponentName`：开始创建指定硬件解码器组件
- `c2.mtk.vp9.decoder`：本次识别到的视频流对应 VP9 硬解
- `setState: 1`：解码器进入初始创建状态
- `Created component`：组件创建成功，系统已识别视频流类型并开始分配对应硬件解码资源

### 2. 初始化配置参数

```text
15405:04-16 15:33:34.814 23653 28260 D MediaCodec: [0xb400007489aed670] setState: 2
15406:04-16 15:33:34.817 23653 28237 D MediaCodec: MediaCodec::init,name:c2.mtk.vp9.decoder
15448:04-16 15:33:34.823 23653 28261 D CCodecConfig:   c2::u32 raw.size.height = 1012
15449:04-16 15:33:34.823 23653 28261 D CCodecConfig:   c2::u32 raw.size.width = 1920
```

字段解读：
- `setState: 2`：进入初始化配置阶段
- `MediaCodec::init`：开始初始化指定解码器
- `raw.size.height/raw.size.width`：送入解码器的原始分辨率信息
- 可通过分辨率、参数规模判断是否存在超 spec 风险

### 3. 开始解码播放

```text
20553:04-16 15:52:44.028 23653 30657 D MediaCodec: [0xb400007489aed670] setState: 5
15528:04-16 15:33:34.836   950 28265 D C2MtkVdec: [0xE3880010] VCodec started.
15529:04-16 15:33:34.838 23653 28261 D CCodecBufferChannel: [c2.mtk.vp9.decoder#718] Created input block pool with allocatorID 16 => poolID 20 - OK (0)
15532:04-16 15:33:34.840 23653 28261 I CCodecBufferChannel: [c2.mtk.vp9.decoder#718] Created output block pool with allocatorID 18 => poolID 164 - OK
```

字段解读：
- `setState: 5`：解码器进入可工作状态
- `VCodec started`：底层视频解码器正式启动
- `Created input block pool`：为压缩码流分配输入缓冲池
- `Created output block pool`：为解码后帧分配输出缓冲池
- 说明解码器已准备接收并处理视频数据

### 4. 输入数据流与格式变更

```text
15612:04-16 15:33:35.988 23653 28260 D CCodecBufferChannel: [c2.mtk.vp9.decoder#718] send inputSlots num:4 to codec
15648:04-16 15:33:36.032   950 28262 D C2MtkVdec: [0xE3880010] FormatChange: width 1920, height 1024, mColorFormat 0x7f000001, crop(Width 1920, Height 1012, Left 0, Top 0, BufferCount 20 -> 24)
15682:04-16 15:33:36.049 23653 28261 D CCodecBuffers: [c2.mtk.vp9.decoder#718:2D-Output] popFromStashAndRegister: at 1000000000000us, output format changed to AMessage(what = 0x00000000) = {
```

字段解读：
- `send inputSlots num:4 to codec`：开始向解码器送入压缩视频数据
- `FormatChange`：解码器解析码流后确认实际输出格式
- `width/height`：输出图像尺寸
- `mColorFormat`：输出颜色格式
- `crop(...)`：实际裁剪区域，可辅助判断是否存在显示异常或花屏风险
- `BufferCount 20 -> 24`：缓冲区数量发生变化，反映运行态资源调整

### 5. 释放与销毁

```text
21788:04-16 15:52:48.775 23653 30628 D MediaCodec: [0xb400007489aed670] [c2.mtk.avc.decoder] releaseAsync
21813:04-16 15:52:48.778 23653 30657 D MediaCodec: [0xb400007489aed670] setState: 10
21881:04-16 15:52:48.796   950 30662 D C2MtkVdec: [0xE3880010] VCodec destroyed.
21911:04-16 15:52:48.800 23653 30657 D MediaCodec: ~MediaCodec(0xb400007489aed670)
```

字段解读：
- `releaseAsync`：开始异步释放解码器
- `setState: 10`：进入释放/结束状态
- `VCodec destroyed`：底层视频解码资源销毁完成
- `~MediaCodec(...)`：MediaCodec 对象析构
- 正常结束时可看到完整释放链路；若异常中断可据此判断退出位置
