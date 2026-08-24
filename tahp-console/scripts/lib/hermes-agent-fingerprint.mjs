/**
 * Hermes Agent 环境缓存失效：版本 + pyproject.toml/uv.lock 指纹。
 * 供 ensure-hermes-agent.mjs 与单测使用。
 */
import { createHash } from 'crypto'
import { existsSync, readFileSync } from 'fs'
import { join } from 'path'

export const MARKER_VERSION = 2
export const TARGET_HERMES_VERSION = '0.20.4'
export const TARGET_HERMES_TAG = 'v2026.8.18'

export function readPyprojectVersion(agentDir) {
  const file = join(agentDir, 'pyproject.toml')
  if (!existsSync(file)) return ''
  try {
    const text = readFileSync(file, 'utf-8')
    const match = text.match(/^version\s*=\s*"([^"]+)"/m)
    return match?.[1]?.trim() || ''
  } catch {
    return ''
  }
}

export function hashFile(filePath) {
  if (!existsSync(filePath)) return ''
  return createHash('sha256').update(readFileSync(filePath)).digest('hex')
}

export function computeLockFingerprint(agentDir) {
  const pyproject = hashFile(join(agentDir, 'pyproject.toml'))
  const lock = hashFile(join(agentDir, 'uv.lock'))
  return createHash('sha256').update(`${pyproject}\n${lock}`).digest('hex')
}

export function computeAgentFingerprint(agentDir) {
  return {
    hermesVersion: readPyprojectVersion(agentDir),
    lockFingerprint: computeLockFingerprint(agentDir),
  }
}

export function isCacheFingerprintFresh(cached, fingerprint) {
  if (!cached || !fingerprint) return false
  if (cached.version !== MARKER_VERSION) return false
  if (!cached.hermesVersion || !cached.lockFingerprint) return false
  if (cached.hermesVersion !== fingerprint.hermesVersion) return false
  if (cached.lockFingerprint !== fingerprint.lockFingerprint) return false
  return true
}

export function isAgentFileInsideRoot(filePath, agentDir) {
  if (!filePath || !agentDir) return false
  const file = String(filePath).replace(/\\/g, '/').toLowerCase()
  const root = String(agentDir).replace(/\\/g, '/').replace(/\/+$/, '').toLowerCase()
  return file === `${root}/run_agent.py` || file.startsWith(`${root}/`)
}

export function originCheckPassed(payload, agentDir, expectedVersion) {
  if (!payload?.ok) return false
  if (expectedVersion && payload.version !== expectedVersion) return false
  return isAgentFileInsideRoot(payload.file, agentDir)
}

const ANSI = {
  reset: '\x1b[0m',
  bold: '\x1b[1m',
  cyan: '\x1b[96m',
  green: '\x1b[92m',
  yellow: '\x1b[93m',
  red: '\x1b[91m',
  dim: '\x1b[2m',
  bgGreen: '\x1b[30;102m',
  bgYellow: '\x1b[30;103m',
  bgRed: '\x1b[97;41m',
}

export function shouldColorHermesBanner(env = process.env) {
  if (env.NO_COLOR) return false
  if (env.FORCE_COLOR === '0') return false
  return true
}

/**
 * 启动脚本用的 Hermes 版本横幅。匹配目标版本时绿底，否则黄/红底。
 * @param {{ version?: string, targetVersion?: string, targetTag?: string, agentDir?: string }} info
 */
export function formatHermesVersionBanner(info = {}, { color = true } = {}) {
  const version = String(info.version || '').trim() || 'unknown'
  const targetVersion = String(info.targetVersion || TARGET_HERMES_VERSION).trim()
  const targetTag = String(info.targetTag || TARGET_HERMES_TAG).trim()
  const agentDir = String(info.agentDir || '').trim()
  const matched = version !== 'unknown' && version === targetVersion
  const missing = version === 'unknown'
  const paint = (code, text) => (color ? `${code}${text}${ANSI.reset}` : text)
  const versionBlock = missing
    ? paint(ANSI.bgRed, ` 未检测到版本 `)
    : matched
      ? paint(ANSI.bgGreen, ` ${version} `)
      : paint(ANSI.bgYellow, ` ${version} `)
  const status = missing
    ? paint(ANSI.red, '未找到 hermes-agent-main')
    : matched
      ? paint(ANSI.green, '与工程目标版本一致')
      : paint(ANSI.yellow, `与目标 ${targetVersion} 不一致`)
  const line = paint(ANSI.cyan, '════════════════════════════════════════════════')
  const title = paint(ANSI.bold + ANSI.cyan, '  Hermes Agent')
  const lines = [
    '',
    line,
    `${title}  ${versionBlock}  ${status}`,
    `  工程目标: ${paint(ANSI.bold + ANSI.green, targetVersion)}  上游标签: ${paint(ANSI.cyan, targetTag)}`,
  ]
  if (agentDir) lines.push(`  来源目录: ${paint(ANSI.dim, agentDir)}`)
  lines.push(line, '')
  return lines.join('\n')
}
