# Modem 基线通知：中心 Socket.IO 推送设计（一期）

> **状态**：已实现（一期代码已合入两仓，待联调验收）  
> **日期**：2026-08-12  
> **范围**：`easyadapter_bff`（中心）+ `easyadapter/tahp-console`（本机客户端）  
> **主文档**：本文件  
> **同步副本**：`easyadapter_bff/docs/baseline-notify/DESIGN.md`（内容须保持一致）

---

## 0. 已确认决策

| # | 项 | 决策 |
|---|-----|------|
| 1 | 通道 | **Socket.IO**（与 Console 现有 `socket.io@^4.8.x` 同大版本） |
| 2 | 离线 | 中心持久化；重连后中心 **主动补推未达** |
| 3 | 一期范围 | **仅 Modem**（不接 GKI） |
| 4 | 合入语义 | **只通知，不自动启动** Modem 升级 |
| 5 | TONES 入口 | 生产只打 **中心 BFF**；本机 `/webhook/modem-baseline/notify` 仅调试 |
| 6 | 中心无 `MODEM_BASELINE_NOTIFY_TOKEN` | **不拒绝**（公司内网）；有配置则校验，无配置则放行（与本机现行为一致） |
| 7 | 补推策略 | **分批全量**（`receivedAt` > cursor，每批 20，直到结束；不截断 50） |
| 8 | actor | **允许加 install 后缀** 防同机多开撞 cursor |
| 9 | 部署 | 一期 **单实例** BFF（不做 Redis adapter） |
| 10 | UI | 一期不改 Modem 页；排障靠服务端/客户端日志 |

---

## 1. 目标 / 非目标

### 1.1 目标

1. TONES `POST` 一次到中心 → 所有**在线**本机 EA **秒级**收到并写入 inbox。  
2. 本机当时离线 → 再次连上中心后，由中心 **补推** 尚未确认送达的通知。  
3. 本机 UI/合入流程复用现有「外部通知 → 采用并填入 → 启动 → 确认完成」。  
4. Windows 调试 BFF 与 Linux 正式 BFF 行为一致，仅 URL 不同。

### 1.2 非目标（一期不做）

- GKI 推送、按平台/部门定向房间。  
- 多中心实例 Redis adapter / sticky session。  
- TONES 保证「每人本机已读」。TONES SLA = **中心已入库**。  
- 用定时 `GET notices` 作为业务主路径（禁止业务轮询）。  
- 改 `tools/gki-patch-tool` / modem 合入脚本逻辑。  
- Modem UI 增加「推送已连接」状态灯（二期可选）。

---

## 2. 问题背景与网络约束

本机 EasyAdapter（`tahp-console`）跑在研发 Windows 本机，中心无法主动 HTTP 打到 `localhost:8650`。

因此「中心推客户端」的正确含义是：

> **本机 Console 启动后主动连上中心，保持 Socket.IO 长连接；TONES 打中心后，中心在已建立的连接上扇出推送。**

不是中心反向连接本机，也不是本机定时拉通知列表。

现有本机 webhook（`POST /webhook/modem-baseline/notify`）与 inbox（`external-notices.json`）保留：字段契约复用；生产扇出改走中心。

---

## 3. 架构总览

```
TONES
  │  POST {CENTRAL}/webhook/modem-baseline/notify
  │  Auth: Bearer / X-Modem-Notify-Token（若已配置 MODEM_BASELINE_NOTIFY_TOKEN）
  ▼
easyadapter_bff（Linux 正式 / Windows 调试）
  ├─ 幂等入库  data/.tahp/baseline-notices/notices.json
  ├─ Socket.IO namespace `/baseline-notify`
  │    ├─ 新建 notice → nsp.emit('baseline.notice') 扇出在线客户端
  │    └─ connection / hello → 按 cursor 分批补推未达
  └─ delivery-cursors.json（按 actor 水位）
  ▲
  │  本机出站长连接
  │  auth.token = TAHP_CENTRAL_TOKEN
  │  auth.actor = {localActor}:{installId}
tahp-console（每人本机）
  ├─ bootstrap → startBaselineNotifyClient()
  ├─ on baseline.notice → ingestModemBaselineNotice（幂等，采用中心 noticeId）
  ├─ 成功落盘后 → emit baseline.ack + 更新本机 cursor
  └─ UI 不变（读本机 external-notices.json）
```

| 角色 | 职责 |
|------|------|
| TONES | 基线完成后对中心发 **1 次** notify |
| easyadapter_bff | 权威存储、鉴权、Socket 扇出、重连补推 |
| 本机 tahp-console | 出站长连接、写入本机 inbox、人工确认合入 |
| 本机 webhook | 仅开发模拟 / 单机联调 |

---

## 4. 数据模型

### 4.1 中心权威 Notice

路径：`{TAHP_DATA_ROOT}/.tahp/baseline-notices/notices.json`

```ts
type CentralBaselineNotice = {
  noticeId: string          // 中心生成，全局唯一；本机 ingest 必须采用此 ID
  source: string            // 默认 tones
  sourceId?: string         // 与 source 组成幂等键
  title?: string
  text: string
  platform?: string
  version?: string
  tosVersion?: string
  module: 'modem'           // 一期写死
  payload: Record<string, unknown>
  receivedAt: string        // ISO，由中心生成；补推水位依据
  updatedAt: string
}
```

约束：

- 幂等：存在 `sourceId` 时，`source + sourceId` 命中则返回已有 notice，**`created=false`，不再次 fan-out**。  
- 保留上限：最近 **500** 条（与本机 inbox 截断策略对齐）。  
- `text`：请求体 `text` / `message` 优先；否则 `title + platform + version + tosVersion` 拼接；仍空则 HTTP 400。

### 4.2 送达游标（中心）

路径：`{TAHP_DATA_ROOT}/.tahp/baseline-notices/delivery-cursors.json`

```ts
type DeliveryCursorStore = {
  actors: Record<string, {
    lastAckNoticeId?: string
    lastAckReceivedAt?: string   // ISO，补推主依据
    updatedAt: string
  }>
}
```

补推集合：

```
notices
  .filter(n => n.module === 'modem')
  .filter(n => !cursor.lastAckReceivedAt || n.receivedAt > cursor.lastAckReceivedAt)
  .sort((a, b) => a.receivedAt.localeCompare(b.receivedAt))
```

然后 **分批全量** emit：每批 **20** 条，批间可 `await` 微任务/短 delay（可选，防撑爆），直到发完；最后可选 `baseline.catchup_done`。

水位比较只用中心生成的 `receivedAt`，不用本机时钟。

### 4.3 本机 inbox（已有，增量扩展）

继续使用 `ModemExternalNotice` + `ingestModemBaselineNotice`。

必须增量：

1. 入站若带中心 `noticeId`，本机 **采用该 noticeId**（禁止再随机生成一套导致补推幂等失败）。  
2. 幂等顺序：`source+sourceId`（已有）→ **`noticeId` 已存在则跳过**。  
3. `applied` / `dismissed` **只存在本机**，一期不上报中心。

本机 cursor 落盘（建议）：

`{dataDir}/modem-patch/central-delivery-cursor.json`

重连 `baseline.hello` 带上本机 cursor，与中心已存 cursor **取更新的水位**（防倒退乱补）。

### 4.4 actor 与 installId

```
actor = `{getLocalActor()}:{installId}`
```

- `getLocalActor()`：复用现有 sync actor 逻辑。  
- `installId`：首次启动写入本机稳定文件（如 `{dataDir}/modem-patch/install-id.txt`），随机 8–16 hex，之后只读。  
- 目的：同一用户/主机多开 Console 时，cursor 互不覆盖，避免漏补。

---

## 5. Socket.IO 协议

### 5.1 连接

| 项 | 值 |
|----|-----|
| URL | `{TAHP_CENTRAL_URL}` |
| path | 默认 `/socket.io/` |
| Namespace | `/baseline-notify` |
| Auth（handshake） | `auth: { token, actor }` |
| token | 必须等于中心 `TAHP_CENTRAL_TOKEN` |
| 中心未配置 `TAHP_CENTRAL_TOKEN` | 拒绝所有 socket（与现有 sync 一致） |
| 本机未配置中心 URL/TOKEN | **不连接**，静默（与 sync scheduler 一致） |
| 重连 | `socket.io-client` 自动重连；连上后再发 `baseline.hello` |

依赖版本：BFF 新增 `socket.io@^4.8.3`（与 `tahp-console/package.json` 对齐）；本机用 `socket.io-client`（若尚未在 server 依赖中则新增，版本对齐 4.8.x）。

### 5.2 事件表

| 事件 | 方向 | Payload | 何时 |
|------|------|---------|------|
| `baseline.hello` | C→S | `{ actor, clientVersion?, cursor?: { lastAckReceivedAt?, lastAckNoticeId? } }` | 每次 connect 成功后立即 |
| `baseline.notice` | S→C | `CentralBaselineNotice` | 新通知扇出 **或** 重连补推 |
| `baseline.ack` | C→S | `{ noticeId, receivedAt }` | 本机 **成功写入 inbox 后** |
| `baseline.catchup_done` | S→C | `{ count: number }` | 补推结束（日志用，可选但建议实现） |

**禁止**：客户端定时 `emit` 拉列表当主路径。补推只允许发生在中心处理 `connection` / `baseline.hello` 时。

### 5.3 服务端逻辑

```
io.of('/baseline-notify').use(authByCentralToken)

on connection(socket):
  socket.data.actor = auth.actor || 'unknown@local'

on baseline.hello(payload):
  actor = payload.actor || socket.data.actor
  cursor = mergeNewer(serverCursor[actor], payload.cursor)
  persist cursor
  list = selectCatchup(cursor)   // 全量未达，按 receivedAt asc
  for batch in chunks(list, 20):
    for n in batch: socket.emit('baseline.notice', n)
  socket.emit('baseline.catchup_done', { count: list.length })

on baseline.ack({ noticeId, receivedAt }):
  if receivedAt >= cursor.lastAckReceivedAt (or cursor empty):
    update cursor
    persist
```

### 5.4 新通知 fan-out

```
HTTP ingest(body):
  { notice, created } = store.upsert(...)
  if created:
    nsp.emit('baseline.notice', notice)   // 当前 ns 全部在线 socket
  return 201 | 200
```

幂等命中（`created=false`）：**不广播**。

### 5.5 本机客户端逻辑

```
if !isCentralConfigured(): return
socket = io(url + '/baseline-notify', {
  auth: { token: centralToken, actor },
  reconnection: true,
})
on connect:
  emit('baseline.hello', { actor, cursor: loadLocalCursor() })
on 'baseline.notice':
  ingestModemBaselineNotice(..., { preferNoticeId: notice.noticeId })
  saveLocalCursor(notice)
  emit('baseline.ack', { noticeId, receivedAt })
on shutdown:
  socket.close()
```

日志前缀建议：`[baseline-notify]`（connected / catchup=N / ingest / ack / unauthorized）。

---

## 6. HTTP 接口（TONES / 探测）

挂在 **easyadapter_bff**，路径与本机调试契约对齐。

### 6.1 `POST /webhook/modem-baseline/notify`

```http
POST /webhook/modem-baseline/notify
Content-Type: application/json
Authorization: Bearer <MODEM_BASELINE_NOTIFY_TOKEN>   # 仅当中心已配置该变量时校验
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

| 项 | 约定 |
|----|------|
| Token 未配置 | **放行**（内网） |
| Token 已配置且不匹配 | **401** |
| 成功新建 | **201** + `noticeId`，并 Socket 广播 |
| 幂等命中 | **200** + 已有 `noticeId`，不广播 |
| 无有效 text | **400** `notice_text_required` |

### 6.2 `GET /webhook/modem-baseline/notify`

探测说明 JSON（非业务页）。`note` 须写明：实时送达依赖本机 Console 已连接中心 `/baseline-notify`；离线靠重连补推。

### 6.3 环境变量

| 变量 | 所在 | 用途 |
|------|------|------|
| `TAHP_CENTRAL_TOKEN` | BFF + 本机 | 本机 Socket / sync 鉴权（已有） |
| `TAHP_CENTRAL_URL` | 本机 | 中心地址（已有；正式默认内网 BFF） |
| `MODEM_BASELINE_NOTIFY_TOKEN` | BFF（可选） | TONES 写通知；未配置则不校验 |

TONES 专用 token 与 `TAHP_CENTRAL_TOKEN` **分离**（若配置了前者）；未配置前者时仅靠内网可达性。

---

## 7. 中心 → 本机字段映射

```ts
ingestModemBaselineNotice({
  source: notice.source,
  sourceId: notice.sourceId,
  text: notice.text,
  title: notice.title,
  platform: notice.platform,
  version: notice.version,
  tosVersion: notice.tosVersion,
  // 扩展选项：强制使用中心 ID
}, { preferNoticeId: notice.noticeId })
```

`payload` 可保留中心原始对象便于排障；展示与状态机仍走现有 pending 流程。

---

## 8. 文件级改动清单

### 8.1 `easyadapter_bff`（必须）

| 文件 | 动作 |
|------|------|
| `package.json` | 增加 `socket.io@^4.8.3` |
| `src/config.ts` | 增加 `modemBaselineNotifyToken`（可读 env，可为空） |
| `src/paths.ts` | `baselineNoticesDir()` + `ensureDataDirs` |
| `src/services/baseline-notices-store.ts` | **新建**：notices / cursor / ingest / catchup |
| `src/services/baseline-notify-hub.ts` | **新建**：Socket.IO nsp、auth、hello/ack、broadcast |
| `src/routes/webhook-baseline.ts` | **新建**：GET/POST notify |
| `src/index.ts` | 注册路由；`listen` 后 `attachBaselineNotifyHub(server)` |
| `.env.example` | 补充 `MODEM_BASELINE_NOTIFY_TOKEN` 说明（可选） |
| `README.md` | API 概览增加 webhook + Socket 说明 |
| `docs/baseline-notify/DESIGN.md` | 本设计文档副本 |
| 测试 / smoke | ingest 幂等、token 可选、（可选）socket 脚本 |

### 8.2 `easyadapter/tahp-console`（必须）

| 文件 | 动作 |
|------|------|
| `package.json`（或 server 依赖处） | 确认/新增 `socket.io-client@^4.8.x` |
| `services/tahp/modem-baseline-notices.ts` | `preferNoticeId` + noticeId 幂等 |
| `services/tahp/sync/baseline-notify-client.ts` | **新建**：连接、hello/ack、installId、cursor |
| `services/tahp/sync/index.ts` | export start/stop |
| `index.ts` bootstrap | `startBaselineNotifyClient()` |
| `services/shutdown.ts`（若适用） | `stopBaselineNotifyClient()` |
| `tools/modem-patch-tool/EA_INTEGRATION.md` | 指向本设计；区分中心生产 / 本机调试 |
| `tests/server/modem-baseline-notices.test.ts` | noticeId 幂等用例 |
| 可选 unit | client 映射 / cursor merge |

### 8.3 明确不改

- Modem / GKI Vue 业务流程（一期）。  
- `tools/gki-patch-tool` 核心。  
- quality 上报链路。

---

## 9. 实现步骤（顺序）

### Phase 0 — 准备

1. 确认正式中心 URL、调试 BFF 可启动。  
2. （可选）生成 `MODEM_BASELINE_NOTIFY_TOKEN`；内网也可先不配。  
3. 锁定 `socket.io` / `socket.io-client` 为 **4.8.x**。

### Phase 1 — BFF 存储 + HTTP ingest

1. `baseline-notices-store.ts`  
2. webhook 路由（token 可选校验）  
3. curl POST 验证落盘与幂等  

### Phase 2 — BFF Socket.IO Hub

1. `attachBaselineNotifyHub`  
2. auth / hello 分批补推 / ack / ingest 广播  
3. 临时 client 脚本：连上 → POST → 收到；断线 → POST → 重连 → 补推 → ack 后再重连无重复（或本机幂等）

### Phase 3 — Console 客户端

1. 扩展 ingest（中心 noticeId）  
2. `baseline-notify-client.ts` + bootstrap/shutdown  
3. 实机：中心推送 → Modem 页外部通知可见  

### Phase 4 — 文档

1. 更新 `EA_INTEGRATION.md`  
2. BFF README  
3. 保持两仓 DESIGN 文档同步  

### Phase 5 — 验证门禁

- BFF：`npm run typecheck`（及新增 smoke 若有）  
- Console：相关 `npm test` + `npm run build`  
- 不提交 `.env`、中心/本机 data 落盘、密钥  

---

## 10. 验收用例

| # | 场景 | 期望 |
|---|------|------|
| 1 | curl → 中心 POST，无本机在线 | 201，落盘 |
| 2 | 本机已连 → POST | 本机 inbox 秒级出现 pending |
| 3 | 同 `sourceId` 再 POST | 200，本机不增重复条 |
| 4 | 本机关闭 → POST → 再开 | 重连补推，inbox 有该条 |
| 5 | ack 后再重连 | 不再重复插入（或幂等吞掉） |
| 6 | 已配错误 NOTIFY_TOKEN | 401 |
| 7 | 未配 NOTIFY_TOKEN | POST 成功（内网约定） |
| 8 | 错误 CENTRAL_TOKEN 连 Socket | unauthorized / 连不上 |
| 9 | 本机「采用并填入→启动」 | 与现行为一致 |
| 10 | 仅打本机 webhook | 调试仍可用，与中心无关 |
| 11 | 同机多开（不同 installId） | 各自补推互不踩 cursor |

---

## 11. 两套环境

| 环境 | 中心 | TONES / 模拟 | 本机配置 |
|------|------|--------------|----------|
| 正式 | Linux `easyadapter_bff` | POST 正式中心 webhook | `TAHP_CENTRAL_URL` → 正式中心 |
| Windows 调试 | 本机/调试机 BFF `:8660` | curl/Postman 模拟 TONES | `TAHP_CENTRAL_URL=http://localhost:8660` |

---

## 12. 风险与约束

| 风险 | 最坏 | 缓解 |
|------|------|------|
| Socket 鉴权缺陷 | 内网任意人收通知 | handshake 校验 `TAHP_CENTRAL_TOKEN` |
| 落盘损坏 | 丢通知 / 异常补推 | try/catch；保留 500 上限 |
| 未 ack 反复补推 | 刷屏 | 本机双幂等 + ack 抬水位 |
| socket.io 主版本不一致 | 连不上 | 锁 4.8.x |
| BFF 多实例 | 只推到连在该实例的客户端 | 一期单实例部署 |
| Console 未启动 | 收不到实时推 | 重连分批全量补推 |
| CORS 收紧后握手失败 | 本机连不上 | 生产收敛 CORS 时覆盖 socket 来源 |

TONES SLA 文案建议：**「通知已进入 EasyAdapter 中心」**，非「已送达每一位研发本机」。

---

## 13. 二期候选（明确不做于一期）

- `module: 'gki'` 共用通道。  
- UI 连接状态灯。  
- 多实例 Redis adapter。  
- 按 platform 定向推送。  
- 本机 applied/dismissed 回传中心。  

---

## 14. 相关文档

- 本机调试 webhook 说明：`tools/modem-patch-tool/EA_INTEGRATION.md`  
- 中心 BFF 角色：`easyadapter_bff/README.md`  
- 本设计同步副本：`easyadapter_bff/docs/baseline-notify/DESIGN.md`  

---

## 15. 变更记录

| 日期 | 说明 |
|------|------|
| 2026-08-12 | 初版定稿：Socket.IO 推送 + 分批全量补推 + install 后缀 actor；NOTIFY_TOKEN 可选 |
| 2026-08-12 | 一期实现：BFF webhook/store/hub + Console baseline-notify-client；单测与 build 通过 |
