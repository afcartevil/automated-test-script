/**
 * 从远端 Samba / 本机映射盘解析 ea-build 落盘位置（纯函数，便于单测）。
 */
export const SAMBA_SHARE_LOOKUP_CMD = 'whoami; echo ===SMB===; testparm -s'

export function parseRemoteWhoami(output: string): string {
  const before = String(output || '').split(/===SMB===/)[0] || ''
  const lines = before.split(/\r?\n/).map(l => l.trim()).filter(Boolean)
  for (const line of lines) {
    if (/^[A-Za-z0-9._-]+$/.test(line)) return line
  }
  throw new Error('无法从远端输出解析 whoami')
}

function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/** 从 testparm 输出取当前用户 share 的 path= */
export function parseSambaSharePath(output: string, user?: string): string {
  const text = String(output || '')
  const who = String(user || '').trim() || parseRemoteWhoami(text)
  const oneLine = text.match(new RegExp(`\\[${escapeRegExp(who)}\\]\\s+path\\s*=\\s*(\\/\\S+)`, 'i'))
  if (oneLine?.[1]) return oneLine[1].replace(/\/+$/, '')
  const block = text.match(new RegExp(`\\[${escapeRegExp(who)}\\]([^\\[]*)`, 'i'))
  const chunk = block?.[1] ?? ''
  const pathLine = chunk.match(/path\s*=\s*(\/\S+)/i)
  if (pathLine?.[1]) return pathLine[1].replace(/\/+$/, '')
  throw new Error(`未在 Samba 配置中找到 [${who}] 的 path=`)
}

export function linuxEaBuildDir(sambaRoot: string): string {
  const root = String(sambaRoot || '').trim().replace(/\/+$/, '')
  if (!root.startsWith('/')) throw new Error(`无效的 Samba 路径: ${sambaRoot}`)
  return `${root}/ea-build`
}

export function normalizeWindowsMapDrive(raw: string): string {
  const trimmed = String(raw || '').trim()
  if (!trimmed) return 'Z:\\'
  if (/^[A-Za-z]:\\?$/.test(trimmed)) return `${trimmed[0].toUpperCase()}:\\`
  if (/^[A-Za-z]:[\\/]/.test(trimmed)) {
    return `${trimmed[0].toUpperCase()}:\\`
  }
  return trimmed.endsWith('\\') || trimmed.endsWith('/') ? trimmed : `${trimmed}\\`
}

export function windowsEaBuildDir(mapDrive: string): string {
  const root = normalizeWindowsMapDrive(mapDrive)
  if (root.endsWith('\\') || root.endsWith('/')) return `${root}ea-build`
  return `${root}\\ea-build`
}

/** 测试可用 TAHP_TEST_EA_BUILD_WIN 覆盖完整 ea-build 目录 */
export function resolveEaBuildWinDir(mapDrive?: string): string {
  const test = String(process.env.TAHP_TEST_EA_BUILD_WIN || '').trim()
  if (test) return test
  return windowsEaBuildDir(mapDrive || 'Z:\\')
}
