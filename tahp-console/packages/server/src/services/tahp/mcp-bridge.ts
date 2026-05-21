/**
 * 最小化 MCP stdio JSON-RPC 客户端 — 桥接到 tahp-mcp-server/server.py.
 *
 * 协议:
 *   - MCP stdio 传输 = 行分隔 JSON-RPC 2.0
 *   - 启动后立即 initialize → initialized → 可发 tools/list, tools/call
 *   - notifications/message (logging) 中带 task_id/phase/progress → 转发到 TaskStream
 */
import { spawn, ChildProcess } from 'child_process'
import { EventEmitter } from 'events'
import { existsSync } from 'fs'
import { tahpPaths, hasTahpProject } from './paths'
import { logger } from '../logger'

interface JsonRpcRequest {
  jsonrpc: '2.0'
  id: number
  method: string
  params?: unknown
}

interface JsonRpcResponse {
  jsonrpc: '2.0'
  id: number
  result?: unknown
  error?: { code: number; message: string; data?: unknown }
}

interface JsonRpcNotification {
  jsonrpc: '2.0'
  method: string
  params?: unknown
}

type JsonRpcMessage = JsonRpcResponse | JsonRpcNotification

interface PendingCall {
  resolve: (result: unknown) => void
  reject: (err: Error) => void
  method: string
  timer: NodeJS.Timeout | null
}

const CALL_TIMEOUT_MS = 600_000

export class McpBridge extends EventEmitter {
  private child: ChildProcess | null = null
  private idCounter = 0
  private pending = new Map<number, PendingCall>()
  private buffer = ''
  private ready = false
  private startPromise: Promise<void> | null = null
  private restartScheduled = false

  /** 启动子进程并完成 initialize 握手。重复调用幂等。 */
  async start(): Promise<void> {
    if (this.ready) return
    if (this.startPromise) return this.startPromise
    this.startPromise = this.doStart()
    try {
      await this.startPromise
    } finally {
      this.startPromise = null
    }
  }

  private async doStart(): Promise<void> {
    if (!hasTahpProject()) {
      throw new Error(`tahp-mcp-server 未找到: ${tahpPaths.mcpServer}。设 TAHP_PROJECT_ROOT 或 TAHP_MCP_SERVER`)
    }
    if (!existsSync(tahpPaths.mcpServer)) {
      throw new Error(`MCP server 文件不存在: ${tahpPaths.mcpServer}`)
    }

    logger.info({ python: tahpPaths.python, server: tahpPaths.mcpServer }, '[tahp-mcp] spawning')
    const child = spawn(tahpPaths.python, [tahpPaths.mcpServer], {
      cwd: tahpPaths.projectRoot,
      stdio: ['pipe', 'pipe', 'pipe'],
      env: {
        ...process.env,
        PYTHONUNBUFFERED: '1',
        PYTHONIOENCODING: 'utf-8',
      },
      windowsHide: true,
    })
    this.child = child

    child.stdout!.setEncoding('utf-8')
    child.stdout!.on('data', (chunk: string) => this.onStdout(chunk))
    child.stderr!.setEncoding('utf-8')
    child.stderr!.on('data', (chunk: string) => {
      // server.py 把日志写到 stderr — 留作可读, 不当作 RPC
      const text = chunk.toString()
      if (text.trim()) logger.debug({ src: 'tahp-mcp' }, text.trim())
    })
    child.on('error', (err) => {
      logger.error({ err }, '[tahp-mcp] child error')
      this.failAllPending(err)
      this.cleanup()
    })
    child.on('exit', (code, signal) => {
      logger.warn({ code, signal }, '[tahp-mcp] child exited')
      this.failAllPending(new Error(`MCP server 进程退出 code=${code} signal=${signal}`))
      this.cleanup()
      this.scheduleRestart()
    })

    // initialize 握手
    const initResp = await this.request('initialize', {
      protocolVersion: '2024-11-05',
      capabilities: {
        roots: { listChanged: false },
        sampling: {},
      },
      clientInfo: {
        name: 'tahp-console-bff',
        version: '0.1.0',
      },
    })
    logger.info({ server: initResp }, '[tahp-mcp] initialize ok')

    // initialized 通知
    this.notify('notifications/initialized')

    this.ready = true
    this.emit('ready')
  }

  private cleanup() {
    this.ready = false
    this.child = null
    this.buffer = ''
  }

  private scheduleRestart() {
    if (this.restartScheduled) return
    this.restartScheduled = true
    setTimeout(() => {
      this.restartScheduled = false
      this.start().catch((err) => {
        logger.warn({ err: err.message }, '[tahp-mcp] auto-restart failed')
      })
    }, 3000)
  }

  private failAllPending(err: Error) {
    for (const [id, p] of this.pending) {
      if (p.timer) clearTimeout(p.timer)
      p.reject(err)
      this.pending.delete(id)
    }
  }

  private onStdout(chunk: string) {
    this.buffer += chunk
    let idx: number
    while ((idx = this.buffer.indexOf('\n')) >= 0) {
      const line = this.buffer.slice(0, idx).trim()
      this.buffer = this.buffer.slice(idx + 1)
      if (!line) continue
      try {
        const msg = JSON.parse(line) as JsonRpcMessage
        this.handleMessage(msg)
      } catch (err) {
        logger.warn({ err, line: line.slice(0, 200) }, '[tahp-mcp] parse failed')
      }
    }
  }

  private handleMessage(msg: JsonRpcMessage) {
    if ('id' in msg && typeof msg.id === 'number') {
      const pending = this.pending.get(msg.id)
      if (!pending) {
        logger.warn({ id: msg.id }, '[tahp-mcp] orphan response')
        return
      }
      this.pending.delete(msg.id)
      if (pending.timer) clearTimeout(pending.timer)
      if (msg.error) pending.reject(new Error(`MCP error ${msg.error.code}: ${msg.error.message}`))
      else pending.resolve(msg.result)
      return
    }
    // notification
    const note = msg as JsonRpcNotification
    this.emit('notification', note)
    // logging / progress 转发
    if (note.method === 'notifications/message') this.emit('log', note.params)
    else if (note.method === 'notifications/progress') this.emit('progress', note.params)
  }

  private nextId(): number {
    this.idCounter += 1
    return this.idCounter
  }

  private write(payload: object) {
    if (!this.child || !this.child.stdin || this.child.stdin.destroyed) {
      throw new Error('MCP server 未启动')
    }
    this.child.stdin.write(JSON.stringify(payload) + '\n', 'utf-8')
  }

  async request(method: string, params?: unknown): Promise<unknown> {
    if (!this.child) await this.start()
    const id = this.nextId()
    const req: JsonRpcRequest = { jsonrpc: '2.0', id, method, params }
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id)
        reject(new Error(`MCP call ${method} 超时 (${CALL_TIMEOUT_MS}ms)`))
      }, CALL_TIMEOUT_MS)
      this.pending.set(id, { resolve, reject, method, timer })
      try {
        this.write(req)
      } catch (err) {
        clearTimeout(timer)
        this.pending.delete(id)
        reject(err as Error)
      }
    })
  }

  notify(method: string, params?: unknown) {
    const note: JsonRpcNotification = { jsonrpc: '2.0', method, params }
    try { this.write(note) } catch (err) { logger.warn({ err }, '[tahp-mcp] notify failed') }
  }

  async listTools(): Promise<unknown> {
    await this.start()
    return this.request('tools/list')
  }

  async callTool(name: string, args: Record<string, unknown>): Promise<unknown> {
    await this.start()
    return this.request('tools/call', { name, arguments: args })
  }

  isReady(): boolean { return this.ready }

  async stop(): Promise<void> {
    this.failAllPending(new Error('Bridge stopped'))
    if (this.child) {
      try { this.child.kill() } catch {}
    }
    this.cleanup()
  }
}

// 单例
let _bridge: McpBridge | null = null
export function getMcpBridge(): McpBridge {
  if (!_bridge) _bridge = new McpBridge()
  return _bridge
}
