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
- 远程执行：`harness_bridge.py` 自动探测 CLI 形态
  - 新 ASF：`asf bridge up` + `asf bridge cmd`（无 `remote-runner bridge-exec`）
  - 旧 Harness：`remote-runner bridge-exec`
- 运行数据、日志、任务记录不写回本目录，而是由 `tahp-console` 服务端写入自己的数据目录

### 外部通知接入（基线完成后推送）

> **生产扇出**：MergeTool → **中心 `easyadapter_bff`** 一次 POST → 中心经 Socket.IO `/baseline-notify` 推到各本机 Console。  
> 完整方案见：[BASELINE_NOTIFY_PUSH_DESIGN.md](./BASELINE_NOTIFY_PUSH_DESIGN.md)。  
> 本机 `POST /webhook/modem-baseline/notify` 仅用于单机调试；生产请打中心同名路径。

MergeTool 完成基线升级后推送通知；**不会自动启动** Modem 升级。研发在 Console「Modem升级」页「采用并填入」后仍保留在待确认；核对并启动后再点「确认完成」才会从列表消失。

```http
POST /webhook/modem-baseline/notify
Content-Type: application/json
Authorization: Bearer <MODEM_BASELINE_NOTIFY_TOKEN>   # 若已配置该环境变量则校验；未配置则放行（内网）
# 或 Header: X-Modem-Notify-Token: <token>
```

请求体（MergeTool 只发这三项；`source` / `sourceId` 由中心补全后再推本机）：

```json
{
  "trunk": "tOS_mtk_A16_vnd_trunk.xml",
  "newBaseline": "t-alps-release-b0.mp1.rc-V12.9.xml",
  "oldBaseline": "t-alps-release-b0.mp1.rc-V11.9.xml"
}
```

中心写入并扇出到本机：

```json
{
  "source": "MergeTool",
  "sourceId": "baseline-job-20260903-001",
  "trunk": "tOS_mtk_A16_vnd_trunk.xml",
  "newBaseline": "t-alps-release-b0.mp1.rc-V12.9.xml",
  "oldBaseline": "t-alps-release-b0.mp1.rc-V11.9.xml"
}
```

- `trunk` / `newBaseline` / `oldBaseline` **均必填**
- `source` 固定 `MergeTool`；`sourceId` 由中心生成 `baseline-job-YYYYMMDD-NNN`（MergeTool 不传）
- inbox 展示为：
  ```text
  任务：tOS_mtk_A16_vnd_trunk.xml 基线升级
  新基线：t-alps-release-b0.mp1.rc-V12.9.xml
  老基线：t-alps-release-b0.mp1.rc-V11.9.xml
  ```
- 从 `newBaseline` 文件名提取版本（如 `V12.9`）供「采用并填入」
- 相同 `trunk` + `newBaseline` + `oldBaseline` 幂等（MergeTool 重试不重复）；成功：`201`（新建）或 `200`（幂等命中）
- 缺字段：`400` `notice_fields_required`

环境变量：`MODEM_BASELINE_NOTIFY_TOKEN`（可选；未配置时不校验 token）

### 维护约束
- 该目录作为 EA 内集成版本，后续对 Modem Patch Tool 的修改应优先在这里进行
- 不提交本机缓存、运行历史、`node_modules`、`__pycache__`、`.env` 等运行态文件
