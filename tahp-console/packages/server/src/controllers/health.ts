import { existsSync, readFileSync } from 'fs'
import { resolve } from 'path'
import * as hermesCli from '../services/hermes/hermes-cli'
import { getAgentBridgeManager } from '../services/hermes/agent-bridge'

declare const __APP_VERSION__: string

type PackageInfo = {
  name: string
  version: string
}

function readPackageInfo(): PackageInfo | null {
  const candidatePaths = [
    // ts-node dev: packages/server/src/controllers -> repo root
    resolve(__dirname, '../../../../package.json'),
    // bundled server: dist/server -> repo root/package root
    resolve(__dirname, '../../package.json'),
    // fallback for dev/test processes started at the repo root
    resolve(process.cwd(), 'package.json'),
  ]

  for (const packagePath of candidatePaths) {
    if (!existsSync(packagePath)) continue

    try {
      const pkg = JSON.parse(readFileSync(packagePath, 'utf-8'))
      if (pkg?.name && pkg?.version) {
        return {
          name: String(pkg.name),
          version: String(pkg.version),
        }
      }
    } catch {
      // Try the next candidate path.
    }
  }

  return null
}

const PACKAGE_INFO = readPackageInfo()
const LOCAL_VERSION = typeof __APP_VERSION__ !== 'undefined'
  ? __APP_VERSION__
  : PACKAGE_INFO?.version || ''

let cachedLatestVersion = ''
let cachedHermesVersion = ''
let cachedHermesVersionAt = 0
const HERMES_VERSION_CACHE_MS = 60_000

async function refreshHermesVersion(): Promise<string> {
  try {
    const raw = await hermesCli.getVersion()
    cachedHermesVersion = raw.split('\n')[0].replace('Hermes Agent ', '') || ''
  } catch {
    cachedHermesVersion = cachedHermesVersion || ''
  }
  cachedHermesVersionAt = Date.now()
  return cachedHermesVersion
}

/** 后台预热 Hermes 版本，避免 /health 首次探测阻塞 dev 启动 */
export function prefetchHermesVersion(): void {
  if (Date.now() - cachedHermesVersionAt < HERMES_VERSION_CACHE_MS && cachedHermesVersion) return
  void refreshHermesVersion()
}

export async function checkLatestVersion(): Promise<void> {
  try {
    const packageName = PACKAGE_INFO?.name || 'hermes-web-ui'
    const registryName = encodeURIComponent(packageName)
    const res = await fetch(`https://registry.npmjs.org/${registryName}/latest`, { signal: AbortSignal.timeout(10000) })
    if (res.ok) {
      const data = await res.json() as { version: string }
      cachedLatestVersion = data.version
      if (LOCAL_VERSION && cachedLatestVersion !== LOCAL_VERSION) {
        console.log(`Update available: ${LOCAL_VERSION} → ${cachedLatestVersion}`)
      }
    }
  } catch { /* ignore */ }
}

export function startVersionCheck(): void {
  setTimeout(checkLatestVersion, 5000)
  setInterval(checkLatestVersion, 30 * 60 * 1000)
}

export async function healthCheck(ctx: any) {
  const now = Date.now()
  const versionStale = now - cachedHermesVersionAt >= HERMES_VERSION_CACHE_MS
  if (!cachedHermesVersion || versionStale) {
    void refreshHermesVersion()
  }
  const agentBridge = getAgentBridgeManager().running ? 'running' : 'stopped'
  ctx.body = {
    status: 'ok',
    platform: 'hermes-agent',
    version: cachedHermesVersion,
    gateway: 'running',
    agent_bridge: agentBridge,
    webui_version: LOCAL_VERSION,
    webui_latest: cachedLatestVersion,
    webui_update_available: Boolean(LOCAL_VERSION && cachedLatestVersion && cachedLatestVersion !== LOCAL_VERSION),
    node_version: process.versions.node,
  }
}
