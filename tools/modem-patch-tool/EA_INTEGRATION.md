## Modem Patch Tool In EA

该目录是 `EasyAdapter` 内维护的 `Modem Patch Tool` 仓内版本。

### 目录定位
- 工具根目录：`tools/modem-patch-tool`
- `EA` 的 `Modem基线` 页面与后端默认调用这里的脚本和配置
- 不再依赖研发个人机器上的外部 `D:\Software\Modem Patch Tool\...` 路径

### 使用约定
- 默认配置来源：`config/baseline_upgrade.json`
- 合入入口：目标 modem 仓内 `tools/md_merge.sh`（工具只做填参 + 冲突非交互化 + `--apm-continue`）
- 启动脚本：
  - `debug_stop_after_merge.py`
  - `debug_continue_after_merge.py`
- 运行数据、日志、任务记录不写回本目录，而是由 `tahp-console` 服务端写入自己的数据目录

### 外部通知接入（基线完成后推送）

> **生产扇出（已拍板设计）**：TONES → **中心 `easyadapter_bff`** 一次 POST → 中心经 Socket.IO `/baseline-notify` 推到各本机 Console；离线靠重连分批全量补推。  
> 完整方案见：[BASELINE_NOTIFY_PUSH_DESIGN.md](./BASELINE_NOTIFY_PUSH_DESIGN.md)（同步副本：`easyadapter_bff/docs/baseline-notify/DESIGN.md`）。  
> 下文 **本机** `POST /webhook/modem-baseline/notify` 仅用于 **单机调试**；TONES 生产请打中心同名路径。

其它工具完成基线升级后推送通知；**不会自动启动** Modem 升级。研发在 Console「Modem升级」页「采用并填入」后仍保留在待确认；核对并启动后需再点「确认完成」才会从列表消失。

```http
POST /webhook/modem-baseline/notify
Content-Type: application/json
Authorization: Bearer <MODEM_BASELINE_NOTIFY_TOKEN>   # 若已配置该环境变量则校验；未配置则放行（内网）
# 或 Header: X-Modem-Notify-Token: <token>
```

请求体示例：

```json
{
  "source": "tones",
  "sourceId": "baseline-job-20260811-001",
  "title": "基线升级完成",
  "platform": "GEN99-V",
  "version": "V11.35",
  "tosVersion": "tOS16.3.0",
  "text": "7月基线升级 GEN99-V V11.35"
}
```

- `text` / `message` 优先；缺省时由 `title + platform + version + tosVersion` 拼接
- 相同 `source` + `sourceId` 幂等，重复推送返回已有 `noticeId`
- 成功：`201`（新建）或 `200`（幂等命中）
- 浏览器 GET 同路径可探测接口说明（不是网页业务页）

环境变量：`MODEM_BASELINE_NOTIFY_TOKEN`（可选；未配置时不校验 token）

### 维护约束
- 该目录作为 EA 内集成版本，后续对 Modem Patch Tool 的修改应优先在这里进行
- 不提交本机缓存、运行历史、`node_modules`、`__pycache__`、`.env` 等运行态文件
