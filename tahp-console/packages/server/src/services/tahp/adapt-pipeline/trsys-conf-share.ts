/**
 * tOS17 trsys conf.json：从版本共享盘选分支，取 NORMAL 下最新 snapshot 的 conf。
 */
import { existsSync, readdirSync, readFileSync, statSync } from 'fs'
import { join } from 'path'
import { spawnSync } from 'child_process'
import { logger } from '../../logger'
import { tahpPaths } from '../paths'

export const TRSYS_SHARE_HOST = '\\\\10.150.98.24\\sw_ver_dev'
export const TRSYS_SHARE_ROOT = `${TRSYS_SHARE_HOST}\\COMPONENTS\\TR_SYSTEM\\17.0.0`
const NORMAL_DIR = 'NORMAL'

export interface TrsysBranchOption {
  name: string
  label: string
}

export interface TrsysConfResolveResult {
  branch: string
  snapshot: string
  confPath: string
  content: string
}

function readDomainCredentials(): { username: string; password: string } | null {
  const p = join(tahpPaths.projectRoot, '.tahp', 'unified-config.json')
  if (!existsSync(p)) return null
  try {
    const raw = JSON.parse(readFileSync(p, 'utf-8')) as Record<string, unknown>
    const username = String(raw.domain_account || '').trim()
    const password = String(raw.domain_password || '')
    if (!username || !password) return null
    return { username, password }
  } catch {
    return null
  }
}

function tryMapShare(): void {
  if (existsSync(TRSYS_SHARE_ROOT)) return
  const creds = readDomainCredentials()
  if (!creds) {
    throw new Error(`无法访问 ${TRSYS_SHARE_ROOT}，且未配置域账号/密码。`)
  }
  const mapped = spawnSync(
    'net',
    ['use', TRSYS_SHARE_HOST, `/user:${creds.username}`, creds.password],
    { encoding: 'utf-8', windowsHide: true },
  )
  if (existsSync(TRSYS_SHARE_ROOT)) return
  const err = String(mapped.stderr || mapped.stdout || '').trim()
  throw new Error(`无法访问 ${TRSYS_SHARE_ROOT}${err ? `：${err.slice(0, 200)}` : ''}`)
}

export function ensureTrsysShareAccessible(): void {
  if (existsSync(TRSYS_SHARE_ROOT)) return
  tryMapShare()
}

export function pickLatestSnapshotName(
  entries: Array<{ name: string; mtimeMs: number }>,
): string | null {
  const dirs = entries.filter(e => e.name && !e.name.startsWith('.'))
  if (!dirs.length) return null
  dirs.sort((a, b) => {
    if (b.mtimeMs !== a.mtimeMs) return b.mtimeMs - a.mtimeMs
    return b.name.localeCompare(a.name)
  })
  return dirs[0].name
}

export function pickConfJsonPath(
  snapshotRoot: string,
  variant: string,
  exists: (p: string) => boolean = existsSync,
): string | null {
  const v = String(variant || 'userdebug').trim() || 'userdebug'
  const candidates = [
    join(snapshotRoot, v, '.pipe', 'conf.json'),
    join(snapshotRoot, 'user', '.pipe', 'conf.json'),
    join(snapshotRoot, 'userdebug', '.pipe', 'conf.json'),
    join(snapshotRoot, 'user_root', '.pipe', 'conf.json'),
    join(snapshotRoot, 'conf.json'),
  ]
  for (const p of candidates) {
    if (exists(p)) return p
  }
  return null
}

function listSubdirs(dir: string): Array<{ name: string; mtimeMs: number }> {
  return readdirSync(dir, { withFileTypes: true })
    .filter(e => e.isDirectory() && !e.name.startsWith('.'))
    .map(e => {
      const full = join(dir, e.name)
      let mtimeMs = 0
      try { mtimeMs = statSync(full).mtimeMs } catch { /* ignore */ }
      return { name: e.name, mtimeMs }
    })
}

export function listTrsysBranches(): TrsysBranchOption[] {
  ensureTrsysShareAccessible()
  return listSubdirs(TRSYS_SHARE_ROOT)
    .sort((a, b) => a.name.localeCompare(b.name))
    .map(e => ({ name: e.name, label: e.name }))
}

export function resolveLatestTrsysConf(branch: string, variant: string): TrsysConfResolveResult {
  const name = String(branch || '').trim()
  if (!name || /[\\/]/.test(name)) throw new Error('无效的 trsys 分支名')
  ensureTrsysShareAccessible()
  const normal = join(TRSYS_SHARE_ROOT, name, NORMAL_DIR)
  if (!existsSync(normal)) {
    throw new Error(`分支 ${name} 下没有 NORMAL 目录`)
  }
  const snapshot = pickLatestSnapshotName(listSubdirs(normal))
  if (!snapshot) throw new Error(`分支 ${name} 的 NORMAL 下没有构建目录`)
  const snapshotRoot = join(normal, snapshot)
  const confPath = pickConfJsonPath(snapshotRoot, variant)
  if (!confPath) {
    throw new Error(`构建目录 ${snapshot} 内未找到 conf.json`)
  }
  const content = readFileSync(confPath, 'utf-8')
  if (!content.trim()) throw new Error(`conf.json 为空: ${confPath}`)
  logger.info({ branch: name, snapshot, confPath }, '[trsys-conf] resolved conf.json')
  return { branch: name, snapshot, confPath, content }
}
