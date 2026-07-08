import { join, resolve } from 'path'
import { homedir } from 'os'
import { existsSync, readFileSync } from 'fs'

/**
 * 轻量 .env 加载（零依赖）：在读取任何 process.env 前，载入 tahp-console/.env。
 * 仅设置尚未存在的变量，真实环境变量优先级更高。便于本地配置 TAHP_CENTRAL_URL/TOKEN 等。
 */
function loadDotEnv(): void {
  const candidates = [
    resolve(process.cwd(), '.env'),
    resolve(__dirname, '../../../.env'),
  ]
  const seen = new Set<string>()
  for (const file of candidates) {
    if (seen.has(file) || !existsSync(file)) continue
    seen.add(file)
    try {
      for (const rawLine of readFileSync(file, 'utf-8').split(/\r?\n/)) {
        const line = rawLine.trim()
        if (!line || line.startsWith('#')) continue
        const eq = line.indexOf('=')
        if (eq <= 0) continue
        const key = line.slice(0, eq).trim()
        if (!key || process.env[key] !== undefined) continue
        let val = line.slice(eq + 1).trim()
        if ((val.startsWith('"') && val.endsWith('"')) || (val.startsWith("'") && val.endsWith("'"))) {
          val = val.slice(1, -1)
        }
        process.env[key] = val
      }
    } catch { /* 忽略 .env 解析失败，回退纯环境变量 */ }
  }
}

loadDotEnv()

/**
 * Web UI environment variables.
 *
 * Server/listen:
 * - PORT: Web UI listen port. Default: 8648.
 * - BIND_HOST: Web UI bind host. Default: 0.0.0.0.
 * - CORS_ORIGINS: Koa CORS origin setting. Default: *.
 *
 * Web UI storage:
 * - HERMES_WEB_UI_HOME: Web UI data home for auth token, credentials, logs, DB, and default uploads.
 * - HERMES_WEBUI_STATE_DIR: Compatibility alias for HERMES_WEB_UI_HOME.
 *   Default: join(homedir(), '.hermes-web-ui').
 * - UPLOAD_DIR: Upload directory override. Default: join(HERMES_WEB_UI_HOME, 'upload').
 *
 * Auth:
 * - AUTH_DISABLED: Set to 1 or true to disable Web UI auth.
 * - AUTH_TOKEN: Explicit bearer token. If unset, Web UI stores an auto-generated token under HERMES_WEB_UI_HOME.
 *
 * Runtime behavior:
 * - PROFILE: Initial Hermes profile name. Default: default.
 * - GATEWAY_HOST: Default gateway host written into profile config. Default: 127.0.0.1.
 * - HERMES_WEB_UI_STOP_GATEWAYS_ON_SHUTDOWN: Whether Web UI shutdown also stops gateways.
 * - WORKSPACE_BASE: Base directory for workspace browsing. Default: /opt/data/workspace.
 *
 * Limits/logging:
 * - MAX_DOWNLOAD_SIZE: Max file download size. Default: 200MB.
 * - MAX_EDIT_SIZE: Max editable file size. Default: 10MB.
 * - LOG_LEVEL: Server log level. Default: info.
 * - BRIDGE_LOG_LEVEL: Bridge log level. Default: LOG_LEVEL or info.
 */

export function getListenHost(env: Record<string, string | undefined> = process.env): string {
  const host = env.BIND_HOST?.trim()
  return host || '0.0.0.0'
}

export function getWebUiHome(env: Record<string, string | undefined> = process.env): string {
  const appHome = env.HERMES_WEB_UI_HOME?.trim() || env.HERMES_WEBUI_STATE_DIR?.trim()
  return appHome ? resolve(appHome) : join(homedir(), '.hermes-web-ui')
}

function deriveDataDir(env: Record<string, string | undefined> = process.env): string {
  const explicit = env.TAHP_SERVER_DATA_DIR?.trim() || env.TAHP_DATA_DIR?.trim()
  const candidates = [
    explicit ? resolve(explicit) : '',
    // Prefer the source data directory so dev mode and dist mode read the same state.
    resolve(process.cwd(), 'packages', 'server', 'data'),
    resolve(__dirname, '..', 'data'),
    resolve(__dirname, '..', '..', 'packages', 'server', 'data'),
    // Allow dist-only deployments to fall back to bundled runtime assets.
    resolve(process.cwd(), 'dist', 'data'),
  ].filter(Boolean)

  const uniqueCandidates = Array.from(new Set(candidates))
  for (const candidate of uniqueCandidates) {
    if (existsSync(candidate)) return candidate
  }

  return uniqueCandidates[0] || resolve(process.cwd(), 'packages', 'server', 'data')
}

const appHome = getWebUiHome()

export const config = {
  port: parseInt(process.env.PORT || '8648', 10),
  // Default to IPv4 for stable WSL/Windows browser access. Use BIND_HOST=:: explicitly for IPv6.
  host: getListenHost(),
  appHome,
  uploadDir: process.env.UPLOAD_DIR || join(appHome, 'upload'),
  dataDir: deriveDataDir(),
  corsOrigins: process.env.CORS_ORIGINS || '*',

  /**
   * TAHP 中心同步配置。
   * - role: 'local'（默认，研发本机；新建条目/草稿 push 到中心待审，审核接口禁用）
   *         'central'（中心权威源，由 easyadapter_bff 承担，本仓一般不用）
   * - centralUrl: 中心 BFF 基址，如 http://central-host:8660
   * - centralToken: 机器间同步共享 token（与中心 TAHP_CENTRAL_TOKEN 一致）
   * - syncIntervalMs: 增量 pull 间隔，默认 5 分钟；<=0 关闭定时
   */
  tahp: {
    role: (process.env.TAHP_ROLE?.trim() || 'local') as 'local' | 'central',
    centralUrl: process.env.TAHP_CENTRAL_URL?.trim() || '',
    centralToken: process.env.TAHP_CENTRAL_TOKEN?.trim() || '',
    syncIntervalMs: parseInt(process.env.TAHP_SYNC_INTERVAL_MS || '300000', 10),
  },
}
