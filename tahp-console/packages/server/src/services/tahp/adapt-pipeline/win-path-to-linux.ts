/**
 * Windows 映射盘路径 → Linux /work/code/$USER/...（$USER 由远端 shell 展开）
 */
export function winMappedPathToLinuxWorkCode(winPath: string): string {
  const raw = String(winPath ?? '').trim()
  if (!raw) throw new Error('路径为空')

  // Z:\foo 或 Z:/foo
  const drive = raw.match(/^([A-Za-z]):[\\/](.*)$/)
  if (!drive) {
    throw new Error(`需要带盘符的 Windows 路径（如 Z:\\LJ9-push），收到：${raw}`)
  }

  const rest = drive[2]
    .replace(/\\/g, '/')
    .replace(/\/+/g, '/')
    .replace(/^\/+|\/+$/g, '')

  if (!rest) {
    throw new Error(`路径缺少目录名：${raw}`)
  }

  return `/work/code/$USER/${rest}`
}

/** 从 from_os / to_os 解析主版本：'17'、'17.0'、'tOS17' → 17 */
export function parseTosMajor(raw?: string): number | null {
  const s = String(raw ?? '').trim()
  if (!s) return null
  const m = s.match(/(?:t\s*os)?\s*(\d+)/i)
  if (!m) return null
  const n = Number(m[1])
  return Number.isFinite(n) ? n : null
}

/** trsys 仅目标版本 to_os ≥ 17 需要 */
export function needsTrsysForTargetOs(toOs?: string): boolean {
  const major = parseTosMajor(toOs)
  return major != null && major >= 17
}

/** 空路径保持空串；非空走盘符换算 */
export function winMappedPathToLinuxWorkCodeOptional(winPath: string): string {
  const raw = String(winPath ?? '').trim()
  if (!raw) return ''
  return winMappedPathToLinuxWorkCode(raw)
}

/**
 * to_os ≥ 17 才保留用户勾选的 trsys；更低版本一律去掉。
 * 不再因 ROOT 为空自动补 trsys。
 */
export function resolveEzBuildTargets(opts: {
  targets: string[]
  trsysRoot?: string
  toOs?: string
}): string[] {
  const list = [...(opts.targets ?? []).map(t => String(t).trim()).filter(Boolean)]
  if (!needsTrsysForTargetOs(opts.toOs)) {
    return list.filter(t => t !== 'trsys')
  }
  return list
}

/** @deprecated 使用 resolveEzBuildTargets */
export function appendTrsysIfRootMissing(targets: string[], trsysRoot: string): string[] {
  return resolveEzBuildTargets({ targets, trsysRoot, toOs: '17' })
}

/** 拼 ez-build 的 BUILD_TARGET_RAW */
export function composeBuildTargetRaw(targets: string[], needPack: boolean): string {
  const list = [...(targets ?? []).map(t => String(t).trim()).filter(Boolean)]
  if (needPack && !list.includes('pack')) list.push('pack')
  if (!list.length) throw new Error('至少选择一个编译 target，或勾选打包')
  return list.join(',')
}
