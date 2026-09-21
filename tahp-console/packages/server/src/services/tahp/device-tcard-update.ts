/**
 * 质量验测 T卡升级：adb push ZIP 到 /sdcard，再经系统更新 UI 选包确认并点击立即重启。
 */
import { spawn } from 'child_process'
import { existsSync, statSync } from 'fs'
import { basename } from 'path'
import { isZipFile, waitForAdbDevice } from './device-flash'

export const TCARD_REMOTE_DIR = '/sdcard'
export const SYSTEM_UPDATE_ACTIVITY =
  'com.transsion.systemupdate/com.transsion.systemupdate.SystemUpdateActivity'
export const OTA_LOCAL_RESOURCE_ID = 'com.transsion.systemupdate:id/ota_local'
export const FILE_NAME_RESOURCE_ID = 'com.transsion.systemupdate:id/file_name'
export const BTN_POSITIVE_RESOURCE_ID = 'com.transsion.systemupdate:id/btn_positive'
export const REBOOT_NOW_RESOURCE_ID = 'com.transsion.systemupdate:id/reboot_now'

const UI_DUMP_REMOTE = '/sdcard/tcard_ui_dump.xml'
const PUSH_TIMEOUT_MS = 40 * 60 * 1000
const REBOOT_NOW_TIMEOUT_MS = 20 * 60 * 1000
const RECONNECT_TIMEOUT_MS = 10 * 60 * 1000
const UI_STEP_TIMEOUT_MS = 30_000
const FILE_LIST_TIMEOUT_MS = 90_000

export interface TcardUpdateOptions {
  zipPath: string
  zipPaths?: string[]
}

export function tcardZipQueue(options: TcardUpdateOptions): string[] {
  const paths = options.zipPaths?.length ? options.zipPaths : [options.zipPath]
  return [...new Set(paths.map((path) => path.trim()).filter(Boolean))]
}

export interface TcardUpdateResult {
  success: boolean
  remotePath?: string
  error?: string
}

export interface UiDumpNode {
  resourceId: string
  text: string
  bounds: string
}

export function isTcardZipPath(path: string): boolean {
  return isZipFile(path.trim())
}

export function tcardRemotePath(zipPath: string): string {
  return `${TCARD_REMOTE_DIR}/${basename(zipPath.trim())}`
}

export function parseAdbPushPercent(line: string): number | null {
  const match = line.match(/\[\s*(\d+)\s*%\]/)
  if (!match) return null
  const pct = Number(match[1])
  return Number.isFinite(pct) ? Math.min(100, Math.max(0, pct)) : null
}

export function formatAdbPushProgressLine(percent: number, remotePath: string): string {
  const pct = Math.max(0, Math.min(100, Math.round(percent)))
  return `[T卡升级] [${String(pct).padStart(3, ' ')}%] ${remotePath}`
}

export function percentFromSizes(remoteBytes: number, localBytes: number): number {
  if (!(localBytes > 0) || !(remoteBytes >= 0)) return 0
  return Math.max(0, Math.min(100, Math.floor((remoteBytes / localBytes) * 100)))
}

/** adb push 进度用 \\r 原地刷新；按 \\r/\\n 切开才能拿到每一帧百分比。 */
export function consumeAdbOutput(buffer: string, chunk: string): { lines: string[]; rest: string } {
  const parts = `${buffer}${chunk}`.split(/\r\n|\n|\r/)
  const rest = parts.pop() ?? ''
  return {
    lines: parts.map((line) => line.trim()).filter(Boolean),
    rest,
  }
}

const ATTR_RE = /([\w:.-]+)="([^"]*)"/g

function parseUiNodeAttrs(tag: string): UiDumpNode | null {
  const attrs: Record<string, string> = {}
  ATTR_RE.lastIndex = 0
  let match: RegExpExecArray | null
  while ((match = ATTR_RE.exec(tag))) {
    attrs[match[1]] = match[2]
  }
  const resourceId = attrs['resource-id'] || ''
  const bounds = attrs.bounds || ''
  if (!resourceId && !bounds) return null
  return { resourceId, text: attrs.text || '', bounds }
}

export function findAllUiNodes(xml: string): UiDumpNode[] {
  const nodes: UiDumpNode[] = []
  const tagRe = /<node\b[^>]*>/gi
  let match: RegExpExecArray | null
  while ((match = tagRe.exec(xml))) {
    const node = parseUiNodeAttrs(match[0])
    if (node) nodes.push(node)
  }
  return nodes
}

export function findNodesByResourceId(xml: string, resourceId: string): UiDumpNode[] {
  const suffix = resourceId.includes('/') ? resourceId.slice(resourceId.lastIndexOf('/') + 1) : resourceId
  return findAllUiNodes(xml).filter((node) => (
    node.resourceId === resourceId || node.resourceId.endsWith(`/${suffix}`)
  ))
}

export function centerOfBounds(bounds: string): { x: number; y: number } | null {
  const match = bounds.match(/\[(\d+),(\d+)\]\[(\d+),(\d+)\]/)
  if (!match) return null
  const x1 = Number(match[1])
  const y1 = Number(match[2])
  const x2 = Number(match[3])
  const y2 = Number(match[4])
  if (![x1, y1, x2, y2].every(Number.isFinite) || x2 - x1 < 8 || y2 - y1 < 8) return null
  return {
    x: Math.floor((x1 + x2) / 2),
    y: Math.floor((y1 + y2) / 2),
  }
}

export function matchPackageFileNode(nodes: UiDumpNode[], zipName: string): UiDumpNode | null {
  const zip = zipName.trim().toLowerCase()
  if (!zip) return null
  const stem = zip.replace(/\.zip$/i, '')
  let best: { node: UiDumpNode; score: number } | null = null
  for (const node of nodes) {
    const text = node.text.trim().toLowerCase()
    if (!text || !centerOfBounds(node.bounds)) continue
    let score = 0
    if (text === zip) score = 3
    else if (text === stem) score = 2
    else if (text.includes(zip) || (stem && text.includes(stem))) score = 1
    if (score > 0 && (!best || score > best.score)) best = { node, score }
  }
  return best?.node ?? null
}

export function matchZipNode(xml: string, zipName: string): UiDumpNode | null {
  return matchPackageFileNode(findNodesByResourceId(xml, FILE_NAME_RESOURCE_ID), zipName)
    || matchPackageFileNode(findAllUiNodes(xml), zipName)
}

function firstNode(xml: string, resourceId: string): UiDumpNode | null {
  return findNodesByResourceId(xml, resourceId).find((node) => centerOfBounds(node.bounds)) ?? null
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function validateZipPath(zipPath: string): string {
  const trimmed = zipPath.trim()
  if (!trimmed) throw new Error('请先选择 T卡升级 ZIP 包')
  if (!isTcardZipPath(trimmed)) throw new Error('T卡升级仅支持 ZIP 文件')
  if (!existsSync(trimmed) || !statSync(trimmed).isFile()) throw new Error(`ZIP 不存在: ${trimmed}`)
  return trimmed
}

interface AdbRunResult {
  code: number
  stdout: string
  stderr: string
}

function runAdb(
  args: string[],
  options: {
    timeoutMs: number
    onOutput?: (line: string) => void
    shouldAbort?: () => boolean
  },
): Promise<AdbRunResult> {
  return new Promise((resolve) => {
    let settled = false
    let stdout = ''
    let stderr = ''
    let timeoutId: NodeJS.Timeout | null = null
    let abortId: NodeJS.Timeout | null = null
    let pendingOut = ''
    const flushPending = () => {
      const leftover = pendingOut.trim()
      pendingOut = ''
      if (leftover) options.onOutput?.(leftover)
    }
    const finish = (code: number) => {
      if (settled) return
      settled = true
      if (timeoutId) clearTimeout(timeoutId)
      if (abortId) clearInterval(abortId)
      flushPending()
      if (proc && !proc.killed) {
        try { proc.kill() } catch { /* ignore */ }
      }
      resolve({ code, stdout, stderr })
    }

    const proc = spawn('adb', args, {
      stdio: ['ignore', 'pipe', 'pipe'],
      windowsHide: true,
    })
    timeoutId = setTimeout(() => finish(-1), options.timeoutMs)
    if (options.shouldAbort) {
      abortId = setInterval(() => {
        if (options.shouldAbort?.()) finish(-2)
      }, 1000)
    }

    const emitChunk = (chunk: Buffer) => {
      if (!options.onOutput) return
      const { lines, rest } = consumeAdbOutput(pendingOut, chunk.toString('utf8'))
      pendingOut = rest
      for (const line of lines) options.onOutput(line)
    }
    proc.stdout?.on('data', (chunk: Buffer) => {
      stdout += chunk.toString('utf8')
      emitChunk(chunk)
    })
    proc.stderr?.on('data', (chunk: Buffer) => {
      stderr += chunk.toString('utf8')
      emitChunk(chunk)
    })
    proc.on('close', (code) => finish(code ?? 1))
    proc.on('error', () => finish(1))
  })
}

async function adbShell(deviceId: string, shellArgs: string[], timeoutMs = 15_000): Promise<AdbRunResult> {
  return runAdb(['-s', deviceId, 'shell', ...shellArgs], { timeoutMs })
}

async function dumpUiXml(deviceId: string): Promise<string> {
  const dump = await adbShell(deviceId, ['uiautomator', 'dump', UI_DUMP_REMOTE], 30_000)
  if (dump.code !== 0 && !/dumped to/i.test(`${dump.stdout}\n${dump.stderr}`)) return ''
  const xml = ((await adbShell(deviceId, ['cat', UI_DUMP_REMOTE], 30_000)).stdout || '').trim()
  if (!xml.includes('<hierarchy') && !xml.startsWith('<?xml')) return ''
  return xml
}

async function tapBounds(deviceId: string, bounds: string): Promise<boolean> {
  const point = centerOfBounds(bounds)
  if (!point) return false
  const result = await adbShell(deviceId, ['input', 'tap', String(point.x), String(point.y)])
  return result.code === 0
}

async function waitForNode(
  deviceId: string,
  timeoutMs: number,
  match: (xml: string) => UiDumpNode | null,
  shouldAbort?: () => boolean,
): Promise<UiDumpNode | null> {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    if (shouldAbort?.()) return null
    const node = match(await dumpUiXml(deviceId))
    if (node?.bounds) return node
    await sleep(1000)
  }
  return null
}

async function waitAndTap(
  deviceId: string,
  timeoutMs: number,
  match: (xml: string) => UiDumpNode | null,
  failMessage: string,
  shouldAbort?: () => boolean,
): Promise<void> {
  const node = await waitForNode(deviceId, timeoutMs, match, shouldAbort)
  if (shouldAbort?.()) throw new Error('T卡升级已取消')
  if (!node) throw new Error(failMessage)
  await sleep(400)
  if (!(await tapBounds(deviceId, node.bounds))) throw new Error(failMessage)
}

async function startActivity(deviceId: string, component: string): Promise<void> {
  const result = await adbShell(deviceId, ['am', 'start', '-n', component], 20_000)
  if (result.code !== 0) {
    throw new Error(`打开 ${component} 失败: ${(result.stderr || result.stdout).trim()}`)
  }
}

async function waitUntilOffline(
  deviceId: string,
  timeoutMs: number,
  shouldAbort?: () => boolean,
): Promise<boolean> {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    if (shouldAbort?.()) return false
    const listed = await runAdb(['devices'], { timeoutMs: 8_000 })
    const online = listed.stdout.split(/\r?\n/).some((line) => {
      const parts = line.trim().split(/\s+/)
      return parts[0] === deviceId && parts[1] === 'device'
    })
    if (!online) return true
    await sleep(2000)
  }
  return false
}

async function readRemoteFileSize(deviceId: string, remotePath: string): Promise<number | null> {
  const result = await adbShell(deviceId, ['stat', '-c', '%s', remotePath], 4_000)
  const raw = `${result.stdout || ''}\n${result.stderr || ''}`.replace(/\r/g, '\n')
  for (const line of raw.split('\n')) {
    const n = Number.parseInt(line.trim(), 10)
    if (Number.isFinite(n) && n >= 0) return n
  }
  return null
}

async function pushZip(
  deviceId: string,
  localPath: string,
  remotePath: string,
  onLog: (line: string) => void,
  shouldAbort?: () => boolean,
): Promise<void> {
  const localSize = statSync(localPath).size
  let lastPct = -1
  const emitPct = (pct: number) => {
    const clamped = Math.max(0, Math.min(100, pct))
    if (clamped === lastPct) return
    lastPct = clamped
    onLog(formatAdbPushProgressLine(clamped, remotePath))
  }
  emitPct(0)

  let pushFinished = false
  const pushPromise = runAdb(
    ['-s', deviceId, 'push', localPath, remotePath],
    {
      timeoutMs: PUSH_TIMEOUT_MS,
      shouldAbort,
      onOutput: (line) => {
        const pct = parseAdbPushPercent(line)
        if (pct != null) {
          emitPct(pct)
          return
        }
        if (/pushed|skipped|error|fail/i.test(line)) onLog(`[T卡升级] ${line}`)
      },
    },
  ).finally(() => {
    pushFinished = true
  })

  const pollPromise = (async () => {
    if (!(localSize > 0)) return
    while (!pushFinished) {
      if (shouldAbort?.()) return
      try {
        const remoteSize = await readRemoteFileSize(deviceId, remotePath)
        if (remoteSize != null) emitPct(percentFromSizes(remoteSize, localSize))
      } catch {
        // 轮询失败不中断 push
      }
      if (pushFinished) return
      await sleep(200)
    }
  })()

  const [result] = await Promise.all([pushPromise, pollPromise])
  if (shouldAbort?.() || result.code === -2) throw new Error('T卡升级已取消')
  if (result.code === -1) throw new Error('adb push 超时')
  if (result.code !== 0) {
    const detail = (result.stderr || result.stdout || '').trim() || `adb push 退出码 ${result.code}`
    throw new Error(`adb push 失败: ${detail}`)
  }
  emitPct(100)
}

export async function runTcardUpdate(
  deviceId: string,
  options: TcardUpdateOptions,
  onLog: (line: string) => void,
  shouldAbort?: () => boolean,
): Promise<TcardUpdateResult> {
  const abortOrThrow = () => {
    if (shouldAbort?.()) throw new Error('T卡升级已取消')
  }

  try {
    const zipPath = validateZipPath(options.zipPath)
    const zipName = basename(zipPath)
    const remotePath = tcardRemotePath(zipPath)

    onLog(`[T卡升级] 开始推送 ${zipName} -> ${remotePath}`)
    abortOrThrow()
    await pushZip(deviceId, zipPath, remotePath, onLog, shouldAbort)
    abortOrThrow()
    onLog('[T卡升级] 推送完成')

    await adbShell(deviceId, ['input', 'keyevent', '224'])
    await adbShell(deviceId, ['wm', 'dismiss-keyguard'])
    onLog(`[T卡升级] 打开系统更新 ${SYSTEM_UPDATE_ACTIVITY}`)
    await startActivity(deviceId, SYSTEM_UPDATE_ACTIVITY)
    await sleep(2000)

    onLog('[T卡升级] 点击本地升级')
    await waitAndTap(
      deviceId,
      UI_STEP_TIMEOUT_MS,
      (xml) => firstNode(xml, OTA_LOCAL_RESOURCE_ID),
      '未找到本地升级入口',
      shouldAbort,
    )

    onLog('[T卡升级] 点击 file_name')
    await waitAndTap(
      deviceId,
      UI_STEP_TIMEOUT_MS,
      (xml) => firstNode(xml, FILE_NAME_RESOURCE_ID),
      '未找到 file_name',
      shouldAbort,
    )
    await sleep(1500)

    onLog(`[T卡升级] 选择刷机包 ${zipName}`)
    await waitAndTap(
      deviceId,
      FILE_LIST_TIMEOUT_MS,
      (xml) => matchZipNode(xml, zipName),
      `未在系统更新文件列表中找到 ${zipName}`,
      shouldAbort,
    )

    onLog('[T卡升级] 确认安装')
    await waitAndTap(
      deviceId,
      UI_STEP_TIMEOUT_MS,
      (xml) => firstNode(xml, BTN_POSITIVE_RESOURCE_ID),
      '未出现确认安装按钮',
      shouldAbort,
    )
    await sleep(1500)

    onLog(`[T卡升级] 再次打开系统更新 ${SYSTEM_UPDATE_ACTIVITY}`)
    await startActivity(deviceId, SYSTEM_UPDATE_ACTIVITY)

    onLog('[T卡升级] 点击立即重启')
    await waitAndTap(
      deviceId,
      REBOOT_NOW_TIMEOUT_MS,
      (xml) => firstNode(xml, REBOOT_NOW_RESOURCE_ID),
      '等待立即重启按钮超时',
      shouldAbort,
    )

    onLog('[T卡升级] 等待设备重启')
    await waitUntilOffline(deviceId, 90_000, shouldAbort)
    abortOrThrow()
    const reconnected = await waitForAdbDevice(deviceId, RECONNECT_TIMEOUT_MS, 5_000, shouldAbort)
    abortOrThrow()
    if (!reconnected) throw new Error('T卡升级后设备未重新连接')

    onLog('[T卡升级] 完成')
    return { success: true, remotePath }
  } catch (err: any) {
    const error = err?.message || 'T卡升级失败'
    onLog(`[T卡升级] 失败: ${error}`)
    return { success: false, error }
  }
}
