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

/** 拼 ez-build 的 BUILD_TARGET_RAW */
export function composeBuildTargetRaw(targets: string[], needPack: boolean): string {
  const list = [...(targets ?? []).map(t => String(t).trim()).filter(Boolean)]
  if (needPack && !list.includes('pack')) list.push('pack')
  if (!list.length) throw new Error('至少选择一个编译 target，或勾选打包')
  return list.join(',')
}
